#!/usr/bin/env python3
"""Start official Syncthing in an isolated, relay-disabled test profile on macOS or Windows."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

from platform_support import WINDOWS, ProfileLock, binary_name, process_identity

VERSION = 'v2.1.7'
HASHES = {
    ('windows', 'amd64'): '3ce7da770f546a8d02b65b2e7ee31f2a3b8b7c3f990ede045590cca4172ecfe1',
    ('windows', 'arm64'): 'd535ffd611b3af223de64bc5dfc60c378881eb13d5c8ecb1431b7407094c15ff',
    ('macos', 'arm64'): '2df075b463231a307c91da657157beaed06383a941ba7ea04d33d536e3c4af38',
    ('macos', 'amd64'): 'b8be90176d0f24daebae7b5aaddac52ebfae395df6d99f5e0e54656db00868cb',
}


def download_platform(system, machine):
    systems = {'darwin': 'macos', 'win32': 'windows'}
    arches = {'arm64': 'arm64', 'aarch64': 'arm64', 'amd64': 'amd64', 'x86_64': 'amd64'}
    if system not in systems or machine.lower() not in arches:
        raise ValueError('Unsupported OS/architecture; do not guess a download')
    return systems[system], arches[machine.lower()]


def child_environment(environment, bypass_proxy=False):
    isolated = {'sthomedir', 'stconfdir', 'stdatadir', 'stguiaddress', 'stguiapikey'}
    if bypass_proxy:
        isolated.update({'http_proxy', 'https_proxy', 'all_proxy'})
    return {key: value for key, value in environment.items() if key.lower() not in isolated}


def write_state(root, state):
    temporary = root / ('.launcher-state.%d.tmp' % os.getpid())
    temporary.write_text(json.dumps(state), encoding='utf-8')
    os.replace(temporary, root / '.launcher-state.json')


def terminate_child(process):
    if process is None:
        return
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    else:
        process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--peer', default=None)
    parser.add_argument('--binary', type=Path)
    parser.add_argument('--gui-port', type=int, default=8385)
    parser.add_argument('--listen-port', type=int, default=22000)
    parser.add_argument('--no-discovery', action='store_true', help='For isolated LAN tests only')
    parser.add_argument('--sender', action='store_true')
    parser.add_argument('--bypass-proxy-env', action='store_true', help='Only after diagnosing proxy interference; remove proxy variables for this Syncthing child only')
    args = parser.parse_args()
    PEER = args.peer
    if sys.platform not in ('darwin', 'win32'):
        raise SystemExit('此启动器支持 macOS 和 Windows。')
    os.umask(0o077)
    if args.root.is_symlink():
        raise SystemExit('Do not use a symlink profile root.')
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if (root / 'config.xml').exists() and not (root / '.direct-transfer-profile').exists():
        raise SystemExit('Existing unrelated configuration preserved; choose a new dedicated directory.')
    try:
        lock = ProfileLock(root / '.launcher.lock')
    except OSError:
        raise SystemExit('此测试配置已在运行，请使用已打开的终端。')
    previous_state = root / '.launcher-state.json'
    if previous_state.exists():
        previous = json.loads(previous_state.read_text(encoding='utf-8'))
        if previous.get('root') != str(root):
            raise SystemExit('Profile state identity mismatch; no configuration changed.')
        child = previous.get('child')
        if child and process_identity(child['pid']) == child:
            raise SystemExit('An existing Syncthing child still uses this profile; stop it before restarting.')
    # Check before rewriting a profile; another listener must not be mistaken for this instance.
    with socket.socket() as probe:
        probe.settimeout(1)
        if probe.connect_ex(('127.0.0.1', args.gui_port)) == 0:
            raise SystemExit('GUI port is already in use; no configuration changed.')
    binary = root / binary_name()
    if not binary.exists() and args.binary:
        shutil.copy2(args.binary.resolve(), binary)
        binary.chmod(0o700)
    if not binary.exists():
        system, arch = download_platform(sys.platform, platform.machine())
        name = 'syncthing-%s-%s-%s.zip' % (system, arch, VERSION)
        archive = root / name
        print('下载 Syncthing 官方版本并校验 SHA-256…', flush=True)
        subprocess.run(['curl', '-L', '--fail', '--connect-timeout', '10', '--max-time', '180', '-o', str(archive), 'https://github.com/syncthing/syncthing/releases/download/%s/%s' % (VERSION, name)], check=True)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != HASHES[(system, arch)]:
            raise SystemExit('下载校验失败，已停止；不会执行此文件。')
        with zipfile.ZipFile(archive) as zipped:
            member = next(n for n in zipped.namelist() if n.endswith('/' + binary_name()) and len(PurePosixPath(n).parts) == 2)
            binary.write_bytes(zipped.read(member))
        binary.chmod(0o700)
    config = root / 'config.xml'
    fresh = not config.exists()
    marker = root / '.direct-transfer-profile'
    if not fresh and not marker.exists():
        raise SystemExit('Existing unrelated configuration preserved; choose a new dedicated directory.')
    if fresh:
        subprocess.run([str(binary), 'generate', '--home', str(root), '--no-port-probing'], check=True)
    marker.write_text('syncthing-direct-file-transfer\n', encoding='utf-8')
    tree = ET.parse(config)
    document = tree.getroot()
    device_id = subprocess.check_output([str(binary), 'device-id', '--home', str(root)], text=True).strip()
    if fresh:
        for folder in document.findall('folder'):
            document.remove(folder)
    options = document.find('options')

    def set_value(parent, tag, value):
        item = parent.find(tag)
        if item is None:
            item = ET.SubElement(parent, tag)
        item.text = value

    # Explicit transports plus relaysEnabled=false prevent relay fallback.
    for item in list(options.findall('listenAddress')):
        options.remove(item)
    for address in ['tcp4://0.0.0.0:%d' % args.listen_port, 'quic4://0.0.0.0:%d' % args.listen_port]:
        ET.SubElement(options, 'listenAddress').text = address
    for tag, value in {
        'relaysEnabled': 'false', 'natEnabled': 'false' if args.no_discovery else 'true',
        'globalAnnounceEnabled': 'false' if args.no_discovery else 'true', 'localAnnounceEnabled': 'false',
        'startBrowser': 'false', 'urAccepted': '-1', 'crashReportingEnabled': 'false',
        'autoUpgradeIntervalH': '0', 'reconnectionIntervalS': '10',
        'stunKeepaliveStartS': '20', 'stunKeepaliveMinS': '10',
    }.items():
        set_value(options, tag, value)
    gui = document.find('gui')
    set_value(gui, 'address', '127.0.0.1:%d' % args.gui_port)
    folder_id = 'p2p-direct-probe-v1'
    folder = next((f for f in document.findall('folder') if f.get('id') == folder_id), None)
    existing_device_ids = {item.get('id') for item in folder.findall('device')} if folder is not None else set()
    if folder is None:
        defaults = document.find('defaults/folder')
        folder = ET.fromstring(ET.tostring(defaults))
        document.insert(0, folder)
    probe_dir = root / 'probe'
    probe_dir.mkdir(exist_ok=True)
    (probe_dir / '.stfolder').mkdir(exist_ok=True)
    folder.set('id', folder_id)
    folder.set('label', 'Direct connection test (1 MiB)')
    folder.set('path', str(probe_dir))
    folder.set('type', 'sendonly' if args.sender else 'receiveonly')
    for item in list(folder.findall('device')):
        folder.remove(item)
    for shared_id in sorted(existing_device_ids | {device_id}):
        if shared_id:
            ET.SubElement(folder, 'device', {'id': shared_id})
    if not args.sender and PEER:
        if document.find("device[@id='%s']" % PEER) is None:
            device = ET.SubElement(document, 'device', {'id': PEER, 'name': 'Direct-test sender', 'compression': 'metadata'})
            ET.SubElement(device, 'address').text = 'dynamic'
        if PEER not in existing_device_ids:
            ET.SubElement(folder, 'device', {'id': PEER})
    if args.sender:
        testfile = probe_dir / 'direct-test-1MiB.bin'
        if not testfile.exists():
            testfile.write_bytes(os.urandom(1024 * 1024))
        print('测试文件 SHA256=' + hashlib.sha256(testfile.read_bytes()).hexdigest(), flush=True)
    tree.write(config, encoding='utf-8', xml_declaration=True)
    print('\nMY_DEVICE_ID=' + device_id, flush=True)
    print('中继已禁用；初始配置仅含独立测试目录；已有本技能配置中的共享目录会保留。', flush=True)
    print('管理页：http://127.0.0.1:%d ；请保持终端运行，按 Control+C 停止。' % args.gui_port, flush=True)
    if not args.sender and PEER:
        print('请把 MY_DEVICE_ID 发给协调方。对方设备已添加，无需输入临时连接码。', flush=True)
    # Preserve existing proxy paths; configure a Syncthing bypass only if traffic is intercepted.
    env = child_environment(os.environ, args.bypass_proxy_env)
    log = (root / 'syncthing.log').open('a', encoding='utf-8')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    api_key = gui.findtext('apikey')

    def api(endpoint):
        request = urllib.request.Request('http://127.0.0.1:%d/rest/' % args.gui_port + endpoint, headers={'X-API-Key': api_key})
        return json.loads(opener.open(request, timeout=3).read())

    last = None
    process = None

    def request_stop(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, request_stop)
    try:
        # Let the child retain the profile lock if the launcher is forcibly killed.
        process = lock.spawn([str(binary), 'serve', '--home', str(root), '--no-browser', '--no-restart'],
            stdout=log, stderr=subprocess.STDOUT, env=env)
        state = {'root': str(root), 'launcher': process_identity(os.getpid()),
                 'child': process_identity(process.pid)}
        if not state['launcher'] or not state['child']:
            raise RuntimeError('Could not record process identity; stopping instead of leaving an unmanaged child.')
        state['launcher'].update({'rootArgument': str(args.root), 'cwd': str(Path.cwd())})
        write_state(root, state)
        (root / 'launcher.pid').write_text(str(os.getpid()))
        while process.poll() is None:
            try:
                connections = api('system/connections').get('connections', {})
                states = []
                for peer_id, connection in connections.items():
                    if not connection.get('connected'):
                        continue
                    transport = connection.get('type', '')
                    if 'relay' in transport.lower():
                        raise RuntimeError('检测到中继连接，立即停止程序。')
                    if transport.startswith(('tcp-', 'quic-')):
                        states.append('%s %s %s' % (peer_id[:7], transport, connection.get('address', '')))
                state = '; '.join(states) if states else '等待对方上线／建立直连'
                if state != last:
                    print('连接状态：' + state, flush=True)
                    last = state
            except (OSError, ValueError):
                pass
            time.sleep(3)
        raise SystemExit('Syncthing 已退出，请查看 ' + str(root / 'syncthing.log'))
    finally:
        # A second TERM/interrupt during cleanup must not bypass child reaping.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        terminate_child(process)
        lock.close()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n已停止。')
