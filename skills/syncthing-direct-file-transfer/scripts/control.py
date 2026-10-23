#!/usr/bin/env python3
"""Control only an isolated launch.py profile; never print its API key."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

from platform_support import WINDOWS, binary_name, process_identity as native_identity, terminate_identity, windows_arguments


def out(value):
    print(json.dumps(value, ensure_ascii=False, indent=2), flush=True)


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()


def inventory(path, zip_crc=False):
    files = []
    for file in sorted(path.rglob('*')):
        relative = file.relative_to(path)
        if any(part in {'.stfolder', '.stversions'} or part.startswith('.syncthing.') for part in relative.parts):
            continue
        if file.is_symlink():
            raise ValueError('Unexpected symlink; inspect before verifying')
        if file.is_file():
            before = file.stat()
            item = {'path': relative.as_posix(), 'bytes': before.st_size, 'sha256': sha(file)}
            if zip_crc and file.suffix.lower() == '.zip':
                with zipfile.ZipFile(file) as archive:
                    bad = archive.testzip()
                    if bad:
                        raise ValueError('ZIP CRC failed: ' + bad)
                item['zipCRC'] = 'ok'
            after = file.stat()
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                raise ValueError('File changed during verification: ' + str(relative))
            files.append(item)
    return files


def directory_inventory(path):
    directories = []
    for item in sorted(path.rglob('*')):
        relative = item.relative_to(path)
        if any(part in {'.stfolder', '.stversions'} or part.startswith('.syncthing.') for part in relative.parts):
            continue
        if item.is_symlink():
            raise ValueError('Unexpected symlink; inspect before verifying')
        if item.is_dir():
            directories.append(relative.as_posix())
    return directories


def canonical_path(value):
    return isinstance(value, str) and bool(value) and not PurePosixPath(value).is_absolute() and '..' not in PurePosixPath(value).parts and PurePosixPath(value).as_posix() == value


def expected_directories(manifest):
    directories = manifest.get('directories')
    if not isinstance(directories, list) or any(not canonical_path(p) for p in directories) or len(set(directories)) != len(directories) or manifest.get('directoryCount') != len(directories):
        raise ValueError('Invalid source directory manifest; regenerate using this version')
    return sorted(directories)


def expected_files(manifest, folder_id):
    if not isinstance(manifest, dict) or manifest.get('schema') != 'syncthing-direct-manifest-v2' or manifest.get('folderID') != folder_id:
        raise ValueError('Unexpected source manifest schema/folder ID')
    files = manifest.get('files')
    if not isinstance(files, list) or not files:
        raise ValueError('Expected a non-empty source file manifest')
    paths = set(expected_directories(manifest))
    for item in files:
        if not isinstance(item, dict):
            raise ValueError('Invalid source manifest entry')
        path = item.get('path', '')
        if not isinstance(path, str) or not path or PurePosixPath(path).is_absolute() or '..' in PurePosixPath(path).parts or PurePosixPath(path).as_posix() != path or path in paths:
            raise ValueError('Invalid or duplicate manifest path')
        if type(item.get('bytes')) is not int or item['bytes'] < 0 or not isinstance(item.get('sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', item['sha256']):
            raise ValueError('Invalid source size/hash')
        paths.add(path)
    if manifest.get('fileCount') != len(files) or manifest.get('totalBytes') != sum(item['bytes'] for item in files):
        raise ValueError('Source manifest totals do not match file entries')
    return sorted(files, key=lambda f: f['path'])


def require_complete(status, files, directories=()):
    size = sum(file['bytes'] for file in files)
    if status.get('state') != 'idle' or any(status.get(k) for k in ['needBytes', 'needFiles', 'needDirectories', 'needSymlinks', 'needDeletes', 'errors', 'pullErrors']):
        raise ValueError('Transfer not complete and idle')
    if not files or status.get('globalFiles') != len(files) or status.get('localFiles') != len(files) or status.get('globalBytes') != size or status.get('localBytes') != size:
        raise ValueError('Expected source file count/bytes not yet present in both indexes')
    if status.get('globalDirectories') != len(directories) or status.get('localDirectories') != len(directories) or status.get('globalSymlinks', 0) or status.get('localSymlinks', 0):
        raise ValueError('Expected source directory count not yet present in both indexes')


def write_report(destination, report, shared_path):
    if destination.resolve().is_relative_to(shared_path.resolve()):
        raise ValueError('Write manifests/reports outside the shared directory')
    with destination.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def process_identity(pid):
    item = native_identity(pid)
    return {k: item[k] for k in ('started', 'command')} if item else None


def stop_profile(root):
    # Stop must work even when config.xml is malformed or the HTTP API is offline.
    state = json.loads((root / '.launcher-state.json').read_text(encoding='utf-8'))
    if state.get('root') != str(root):
        raise ValueError('Recorded profile identity mismatch; no signal sent')

    def matches(kind):
        item = state.get(kind)
        if not item:
            return False
        identity = process_identity(item['pid'])
        if identity != {k: item[k] for k in ['started', 'command']}:
            return False
        flag = '--root' if kind == 'launcher' else '--home'
        argument = item.get('rootArgument', str(root)) if kind == 'launcher' else str(root)
        origin = Path(item.get('cwd', '/')) / argument
        if WINDOWS:
            argv = windows_arguments(identity['command'])
            has_root = any(arg == flag and i + 1 < len(argv) and argv[i+1] == argument or arg == flag + '=' + argument for i, arg in enumerate(argv))
            prefix = argv[:argv.index('--root')] if '--root' in argv else argv
            program_ok = any(Path(arg).name == 'launch.py' for arg in prefix) if kind == 'launcher' else Path(argv[0]).resolve() == root / binary_name()
        else:
            has_root = bool(re.search(r'(?:^|\s)' + flag + r'(?:=|\s+)' + re.escape(argument) + r'(?=\s|$)', identity['command']))
            program_ok = 'launch.py' in identity['command'] if kind == 'launcher' else str(root / binary_name()) in identity['command']
        if origin.resolve() != root or not has_root or not program_ok:
            raise ValueError('Recorded command does not own this profile')
        return True

    if WINDOWS:
        # Terminate the verified child first; Windows TerminateProcess cannot run Python finally.
        for kind in ('child', 'launcher'):
            if matches(kind):terminate_identity(state[kind], force=True)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if not matches('launcher') and not matches('child'):
                out({'stopped': True, 'profile': str(root)});return
            time.sleep(0.2)
        raise ValueError('Could not confirm stopped Windows processes')
    launcher_running = matches('launcher')
    if launcher_running:
        terminate_identity(state['launcher'])
    elif matches('child'):
        terminate_identity(state['child'])
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline and (matches('launcher') or matches('child')):
        time.sleep(0.1)
    for kind in ['child', 'launcher']:
        if matches(kind):
            terminate_identity(state[kind])
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and (matches('launcher') or matches('child')):
        time.sleep(0.1)
    for kind in ['child', 'launcher']:
        if matches(kind):
            terminate_identity(state[kind], force=True)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and (matches('launcher') or matches('child')):
        time.sleep(0.1)
    if matches('launcher') or matches('child'):
        raise ValueError('Could not confirm stopped processes')
    out({'stopped': True, 'profile': str(root)})


def endpoint(value):
    u = urllib.parse.urlsplit(value)
    if u.scheme not in {'tcp', 'tcp4', 'tcp6', 'quic', 'quic4', 'quic6'} or not u.hostname or not u.port or u.username or u.password or u.path or u.query or u.fragment:
        raise argparse.ArgumentTypeError('Use direct scheme://literal-IP:port')
    ipaddress.ip_address(u.hostname)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ['status', 'offers', 'stop']:
        sub.add_parser(name)
    p = sub.add_parser('peer');p.add_argument('--id', required=True);p.add_argument('--endpoint', type=endpoint, action='append', default=[])
    p = sub.add_parser('probe-share');p.add_argument('--id', required=True)
    p = sub.add_parser('share');p.add_argument('--id', required=True);p.add_argument('--folder-id', required=True);p.add_argument('--path', type=Path, required=True);p.add_argument('--label', default='')
    p = sub.add_parser('accept');p.add_argument('--folder-id', required=True);p.add_argument('--path', type=Path, required=True)
    p = sub.add_parser('pause');p.add_argument('--folder-id', required=True)
    p = sub.add_parser('manifest');p.add_argument('--folder-id', required=True);p.add_argument('--out', type=Path, required=True)
    p = sub.add_parser('verify');p.add_argument('--folder-id', required=True);p.add_argument('--zip-crc', action='store_true');p.add_argument('--report', type=Path)
    expected = p.add_mutually_exclusive_group(required=True)
    expected.add_argument('--manifest', type=Path)
    expected.add_argument('--expected-sha256', help='Sender SHA-256, synthetic 1 MiB probe only')
    p = sub.add_parser('wait');p.add_argument('--id');p.add_argument('--folder-id');p.add_argument('--timeout', type=int, default=60)
    args = parser.parse_args()
    root = args.root.resolve()
    if not (root / '.direct-transfer-profile').exists():
        raise ValueError('Not a dedicated profile created by this skill')
    if args.command == 'stop':
        stop_profile(root)
        return
    config = ET.parse(root / 'config.xml').getroot()
    gui = config.find('gui')
    address = gui.findtext('address')
    if not address.startswith('127.0.0.1:') or gui.get('tls') == 'true':
        raise ValueError('Expected loopback HTTP GUI')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def api(path, data=None, method=None):
        request = urllib.request.Request('http://' + address + '/rest/' + path,
            headers={'X-API-Key': gui.findtext('apikey'), 'Content-Type': 'application/json'},
            data=None if data is None else json.dumps(data).encode(), method=method)
        with opener.open(request, timeout=8) as response:
            b = response.read()
            return json.loads(b) if b else None

    options = api('config/options')
    if options.get('relaysEnabled') is not False or not options.get('listenAddresses') or any(not x.startswith(('tcp://', 'tcp4://', 'tcp6://', 'quic://', 'quic4://', 'quic6://')) for x in options['listenAddresses']):
        raise ValueError('Relay/default listener detected; operation refused')

    def connections():
        if api('config/options').get('relaysEnabled') is not False:
            raise ValueError('Relay setting changed; stopped')
        result = api('system/connections').get('connections', {})
        for c in result.values():
            for item in [c, c.get('primary', {})] + c.get('secondary', []):
                if 'relay' in item.get('type', '').lower():
                    raise ValueError('Unexpected relay transport')
            if c.get('connected') and not c.get('type', '').startswith(('tcp-', 'quic-')):
                raise ValueError('Unexpected connected transport')
        return result

    def require_direct(peer):
        if not connections().get(peer, {}).get('connected'):
            raise ValueError('Verify direct connection and synthetic file first')

    def folder(folder_id):
        return api('config/folders/' + urllib.parse.quote(folder_id, safe=''))

    def set_folder(folder_id, path, kind, peers, label):
        path = path.absolute()
        if path.is_symlink():
            raise ValueError('Shared root cannot be a symlink')
        path = path.resolve()
        existing = next((f for f in api('config/folders') if f['id'] == folder_id), None)
        if existing and Path(existing['path']).resolve() != path:
            raise ValueError('Existing folder path preserved; choose another ID')
        if kind == 'receiveonly' and not existing and path.exists() and any(path.iterdir()):
            raise ValueError('Choose an empty receive destination')
        path.mkdir(parents=True, exist_ok=True)
        data = existing or api('config/defaults/folder')
        devices = sorted(set(peers + [api('system/status')['myID']]))
        data.update({'id': folder_id, 'label': label, 'path': str(path), 'type': kind,
            'paused': False, 'devices': [{'deviceID': d} for d in devices]})
        api('config/folders/' + urllib.parse.quote(folder_id, safe=''), data, 'PUT')
        out({'folderID': folder_id, 'path': str(path), 'type': kind})

    if args.command == 'status':
        status = api('system/status')
        out({'deviceID': status['myID'], 'relaysEnabled': False, 'listeners': status.get('connectionServiceStatus'),
            'discoveryErrors': status.get('discoveryErrors'), 'connections': connections(), 'discovery': api('system/discovery')})
    elif args.command == 'offers':
        out(api('cluster/pending/folders'))
    elif args.command == 'peer':
        data = next((d for d in api('config/devices') if d['deviceID'] == args.id), None)
        data = data or {'deviceID': args.id, 'name': 'Direct transfer peer', 'compression': 'metadata', 'autoAcceptFolders': False}
        if args.endpoint:
            data['addresses'] = list(dict.fromkeys(args.endpoint + ['dynamic']))
        elif not data.get('addresses'):
            data['addresses'] = ['dynamic']
        api('config/devices/' + urllib.parse.quote(args.id, safe=''), data, 'PUT')
        out({'peerID': args.id, 'addresses': data['addresses']})
    elif args.command == 'probe-share':
        path = root / 'probe';file = path / 'direct-test-1MiB.bin'
        if not file.is_file() or file.stat().st_size != 1048576:
            raise ValueError('Launch one sender with --sender to generate the synthetic probe')
        set_folder('p2p-direct-probe-v1', path, 'sendonly', [args.id], 'Synthetic direct test')
        out({'bytes': file.stat().st_size, 'sha256': sha(file)})
    elif args.command == 'share':
        require_direct(args.id)
        if not args.path.is_dir():
            raise ValueError('Specify the authorized dedicated source directory')
        set_folder(args.folder_id, args.path, 'sendonly', [args.id], args.label or args.folder_id)
    elif args.command == 'accept':
        offer = api('cluster/pending/folders').get(args.folder_id)
        if not offer or len(offer.get('offeredBy', {})) != 1:
            raise ValueError('Missing or ambiguous pending offer')
        peer = next(iter(offer['offeredBy']))
        if args.folder_id != 'p2p-direct-probe-v1':
            require_direct(peer)
        set_folder(args.folder_id, args.path, 'receiveonly', [peer], offer['offeredBy'][peer].get('label', args.folder_id))
    elif args.command == 'pause':
        data = folder(args.folder_id);data['paused'] = True
        api('config/folders/' + urllib.parse.quote(args.folder_id, safe=''), data, 'PUT')
        out({'paused': args.folder_id})
    elif args.command == 'manifest':
        data = folder(args.folder_id)
        if data.get('type') != 'sendonly':
            raise ValueError('Create a source manifest on the send-only side')
        path = Path(data['path'])
        files = inventory(path)
        directories = directory_inventory(path)
        require_complete(api('db/status?folder=' + urllib.parse.quote(args.folder_id)), files, directories)
        report = {'schema': 'syncthing-direct-manifest-v2', 'folderID': args.folder_id,
                  'fileCount': len(files), 'directoryCount': len(directories), 'directories': directories,
                  'totalBytes': sum(f['bytes'] for f in files), 'files': files}
        write_report(args.out, report, path)
        out(report)
    elif args.command == 'verify':
        data = folder(args.folder_id);path = Path(data['path'])
        if args.manifest:
            manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
            expected = expected_files(manifest, args.folder_id)
            expected_dirs = expected_directories(manifest)
        else:
            if args.folder_id != 'p2p-direct-probe-v1' or not re.fullmatch(r'[0-9a-f]{64}', args.expected_sha256):
                raise ValueError('Use a source manifest for user files; a sender hash is only sufficient for the fixed synthetic probe')
            expected = [{'path': 'direct-test-1MiB.bin', 'bytes': 1048576, 'sha256': args.expected_sha256}]
            expected_dirs = []
        status = api('db/status?folder=' + urllib.parse.quote(args.folder_id))
        require_complete(status, expected, expected_dirs)
        files = inventory(path, args.zip_crc)
        directories = directory_inventory(path)
        if directories != expected_dirs:
            raise ValueError('Received directory paths differ from the sender expectation')
        actual = [{k: f[k] for k in ['path', 'bytes', 'sha256']} for f in files]
        target = [{k: f[k] for k in ['path', 'bytes', 'sha256']} for f in expected]
        if sorted(actual, key=lambda f: f['path']) != sorted(target, key=lambda f: f['path']):
            raise ValueError('Received file names/sizes/SHA-256 differ from the sender expectation')
        require_complete(api('db/status?folder=' + urllib.parse.quote(args.folder_id)), expected, expected_dirs)
        report = {'folderID': args.folder_id, 'relaysEnabled': False, 'sourceMatched': True, 'files': files, 'directories': directories}
        if args.report:
            write_report(args.report, report, path)
        out(report)
    elif args.command == 'wait':
        if not args.id and not args.folder_id:
            raise ValueError('Provide --id or --folder-id')
        deadline = time.monotonic() + args.timeout
        while True:
            states = connections();checks = []
            if args.id:
                c = states.get(args.id, {});checks.append(bool(c.get('connected')))
                out({k: c.get(k) for k in ['connected', 'address', 'type']})
            if args.folder_id:
                s = api('db/status?folder=' + urllib.parse.quote(args.folder_id))
                out({k: s.get(k) for k in ['state', 'globalFiles', 'globalBytes', 'localFiles', 'localBytes', 'needBytes', 'needFiles', 'needDirectories', 'errors', 'pullErrors']})
                if s.get('errors') or s.get('pullErrors'):
                    raise ValueError('Transfer errors; inspect logs')
                checks.append(s.get('globalFiles', 0) > 0 and s.get('state') == 'idle' and s.get('localFiles') == s.get('globalFiles') and s.get('localBytes') == s.get('globalBytes') and s.get('localDirectories') == s.get('globalDirectories') and not any(s.get(k) for k in ['needBytes', 'needFiles', 'needDirectories', 'needSymlinks', 'needDeletes']))
            if all(checks):
                return
            if time.monotonic() >= deadline:
                raise ValueError('Timed out without relay fallback; inspect before retry')
            time.sleep(min(5, max(0.1, deadline - time.monotonic())))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, ET.ParseError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        print('ERROR:', error, file=sys.stderr)
        sys.exit(1)
