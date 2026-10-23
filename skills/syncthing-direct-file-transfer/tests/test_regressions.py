"""Offline regressions: synthetic profiles, loopback mock API, no real user services."""
import hashlib
import http.server
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
RULE = 'PROCESS-NAME,syncthing,DIRECT'
PROBE = 'p2p-direct-probe-v1'


def command(script, *args, timeout=25):
    return subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)], capture_output=True, text=True, timeout=timeout)


class RuleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='direct rule ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root / 'rules.yaml'
        self.backups = self.root / 'backups'

    def run_rule(self, text):
        self.file.write_text(text)
        return command('clash_rule.py', '--file', self.file, '--backup-dir', self.backups)

    def test_append_is_not_prepend_and_other_rules_survive(self):
        old = 'prepend: []\nappend:\n  - ' + RULE + '\n  - MATCH,PROXY\ndelete: []\n'
        p = self.run_rule(old)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.file.read_text(), 'prepend:\n  - ' + RULE + '\nappend:\n  - ' + RULE + '\n  - MATCH,PROXY\ndelete: []\n')
        self.assertEqual(next(self.backups.iterdir()).read_text(), old)

    def test_explicit_delete_conflict_is_not_success(self):
        old = 'prepend: []\nappend: []\ndelete:\n  - "' + RULE + '"\n'
        p = self.run_rule(old)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('delete', p.stderr)
        self.assertEqual(self.file.read_text(), old)
        self.assertFalse(self.backups.exists())

    def test_shadowed_and_duplicate_rules_move_before_match(self):
        old = 'prepend:\n  # retain this comment\n  - MATCH,PROXY\n  - "' + RULE + '"\n  - ' + RULE + '\nappend: []\ndelete: []\n'
        p = self.run_rule(old)
        self.assertEqual(p.returncode, 0, p.stderr)
        expected = 'prepend:\n  - ' + RULE + '\n  # retain this comment\n  - MATCH,PROXY\nappend: []\ndelete: []\n'
        self.assertEqual(self.file.read_text(), expected)
        before = len(list(self.backups.iterdir()))
        p = command('clash_rule.py', '--file', self.file, '--backup-dir', self.backups)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(self.file.read_text(), expected)
        self.assertEqual(len(list(self.backups.iterdir())), before)

    def test_unsupported_structure_is_not_rewritten(self):
        old = 'prepend: [MATCH, PROXY]\nappend: []\ndelete: []\n'
        self.assertNotEqual(self.run_rule(old).returncode, 0)
        self.assertEqual(self.file.read_text(), old)


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='direct verify ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.shared = self.root / 'received'
        self.shared.mkdir()
        (self.root / '.direct-transfer-profile').write_text('test')
        self.status = {'state': 'idle', 'needBytes': 0, 'needFiles': 0, 'needDeletes': 0, 'errors': 0, 'pullErrors': 0,
                       'globalFiles': 0, 'localFiles': 0, 'globalBytes': 0, 'localBytes': 0, 'globalDirectories': 0, 'localDirectories': 0}
        self.folder_id = PROBE
        self.kind = 'receiveonly'
        test = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/rest/config/options':
                    value = {'relaysEnabled': False, 'listenAddresses': ['tcp4://0.0.0.0:22000']}
                elif self.path.startswith('/rest/config/folders/'):
                    value = {'path': str(test.shared), 'type': test.kind, 'id': test.folder_id}
                elif self.path.startswith('/rest/db/status?'):
                    value = test.status
                elif self.path == '/rest/system/connections':
                    value = {'connections': {'peer': {'connected': True, 'type': 'quic-client'}}}
                else:
                    self.send_error(404);return
                data = json.dumps(value).encode()
                self.send_response(200);self.send_header('Content-Length', str(len(data)));self.end_headers();self.wfile.write(data)
            def log_message(self, *args):
                pass
        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        port = self.server.server_address[1]
        (self.root / 'config.xml').write_text('<configuration><gui tls="false"><address>127.0.0.1:%d</address><apikey>synthetic</apikey></gui></configuration>' % port)

    def control(self, *args):
        return command('control.py', '--root', self.root, *args)

    def set_data(self, mapping):
        for name, data in mapping.items():
            (self.shared / name).write_bytes(data)
        size = sum(len(d) for d in mapping.values())
        self.status.update(globalFiles=len(mapping), localFiles=len(mapping), globalBytes=size, localBytes=size)

    def manifest(self, mapping, name='source.json'):
        self.folder_id = 'user-files'
        entries = [{'path': n, 'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()} for n, b in mapping.items()]
        data = {'schema': 'syncthing-direct-manifest-v2', 'folderID': self.folder_id,
                'fileCount': len(entries), 'totalBytes': sum(e['bytes'] for e in entries), 'files': entries, 'directories': [], 'directoryCount': 0}
        path = self.root / name;path.write_text(json.dumps(data));return path

    def test_empty_index_and_connected_peer_are_not_file_completion(self):
        p = self.control('verify', '--folder-id', PROBE, '--expected-sha256', '0' * 64)
        self.assertNotEqual(p.returncode, 0)
        self.assertNotIn('sourceMatched', p.stdout)
        self.assertNotEqual(self.control('wait', '--id', 'peer', '--folder-id', PROBE, '--timeout', '0').returncode, 0)

    def test_probe_wrong_name_size_or_hash_is_rejected(self):
        data = b'x' * 1048576;expected = hashlib.sha256(data).hexdigest()
        self.set_data({'wrong.bin': data})
        self.assertNotEqual(self.control('verify', '--folder-id', PROBE, '--expected-sha256', expected).returncode, 0)
        (self.shared / 'wrong.bin').rename(self.shared / 'direct-test-1MiB.bin')
        self.assertNotEqual(self.control('verify', '--folder-id', PROBE, '--expected-sha256', '0' * 64).returncode, 0)
        p = self.control('verify', '--folder-id', PROBE, '--expected-sha256', expected)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertTrue(json.loads(p.stdout)['sourceMatched'])

    def test_subset_and_equal_size_corruption_rejected_against_source(self):
        expected = {'a.zip': b'abcd', 'b.zip': b'efgh'};manifest = self.manifest(expected)
        self.set_data({'a.zip': b'abcd'})
        self.assertNotEqual(self.control('verify', '--folder-id', self.folder_id, '--manifest', manifest).returncode, 0)
        self.set_data({'a.zip': b'abcd', 'b.zip': b'xxxx'})
        self.assertNotEqual(self.control('verify', '--folder-id', self.folder_id, '--manifest', manifest).returncode, 0)
        (self.shared / 'b.zip').write_bytes(b'efgh')
        p = self.control('verify', '--folder-id', self.folder_id, '--manifest', manifest)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(len(json.loads(p.stdout)['files']), 2)

    def test_source_manifest_export_and_non_overwrite(self):
        self.kind = 'sendonly';self.folder_id = 'user-files';self.set_data({'a.txt': b'actual source'})
        path = self.root / 'source.json'
        p = self.control('manifest', '--folder-id', self.folder_id, '--out', path)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(path.read_text())['fileCount'], 1)
        self.assertNotEqual(self.control('manifest', '--folder-id', self.folder_id, '--out', path).returncode, 0)
        self.assertNotEqual(self.control('manifest', '--folder-id', self.folder_id, '--out', self.shared / 'manifest.json').returncode, 0)

    def test_empty_directory_paths_and_indexes_are_verified(self):
        mapping = {'a.txt': b'source file'}
        manifest = self.manifest(mapping)
        data = json.loads(manifest.read_text())
        data.update(directories=['empty', 'empty/nested'], directoryCount=2)
        manifest.write_text(json.dumps(data))
        self.set_data(mapping)
        self.assertNotEqual(self.control('verify', '--folder-id', self.folder_id, '--manifest', manifest).returncode, 0)
        self.status.update(globalDirectories=2, localDirectories=2)
        (self.shared / 'wrong').mkdir();(self.shared / 'wrong/nested').mkdir()
        self.assertNotEqual(self.control('verify', '--folder-id', self.folder_id, '--manifest', manifest).returncode, 0)
        (self.shared / 'wrong').rename(self.shared / 'empty')
        result = self.control('verify', '--folder-id', self.folder_id, '--manifest', manifest)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['directories'], ['empty', 'empty/nested'])
        self.status['needDirectories'] = 1
        self.assertNotEqual(self.control('verify', '--folder-id', self.folder_id, '--manifest', manifest).returncode, 0)

    def test_manifest_exports_empty_directories_and_rejects_v1(self):
        self.kind = 'sendonly';self.folder_id = 'user-files';self.set_data({'a.txt': b'source'})
        (self.shared / 'empty').mkdir();self.status.update(globalDirectories=1, localDirectories=1)
        path = self.root / 'directory-source.json'
        result = self.control('manifest', '--folder-id', self.folder_id, '--out', path)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(path.read_text())
        self.assertEqual(data['directories'], ['empty']);self.assertEqual(data['directoryCount'], 1)
        data['schema'] = 'syncthing-direct-manifest-v1';path.write_text(json.dumps(data))
        self.assertNotEqual(self.control('verify', '--folder-id', self.folder_id, '--manifest', path).returncode, 0)


FAKE_BINARY = r'''#!/usr/bin/env python3
import json, os, signal, sys, time
from pathlib import Path
root = Path(sys.argv[sys.argv.index('--home') + 1])
if sys.argv[1] == 'generate':
    (root / 'config.xml').write_text('<configuration><gui tls="false"><address>127.0.0.1:1</address><apikey>test</apikey></gui><options/><defaults><folder id="" path=""/></defaults></configuration>')
elif sys.argv[1] == 'device-id':
    print('SYNTHETIC-ID')
elif sys.argv[1] == 'serve':
    if (root / 'close-inherited-lock').exists():
        target = (root / '.launcher.lock').stat().st_ino
        for fd in range(3, 256):
            try:
                if os.fstat(fd).st_ino == target:os.close(fd)
            except OSError:pass
    while True:time.sleep(.05)
'''


@unittest.skipUnless(sys.platform == 'darwin', 'macOS launcher')
class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='direct lifecycle ')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'profile with spaces'
        self.binary = self.base / 'fake-syncthing'
        self.binary.write_text(FAKE_BINARY);self.binary.chmod(0o700)
        self.children = []
        self.addCleanup(self.cleanup_processes)
        with __import__('socket').socket() as s:
            s.bind(('127.0.0.1', 0));self.port = s.getsockname()[1]

    def cleanup_processes(self):
        for p in self.children:
            if p.poll() is None:
                p.kill()
            p.wait(timeout=5)
        state = self.root / '.launcher-state.json'
        if state.exists():
            pid = json.loads(state.read_text()).get('child', {}).get('pid')
            if pid and self.running(pid):
                os.kill(pid, signal.SIGKILL)

    def running(self, pid):
        p = subprocess.run(['ps', '-p', str(pid), '-o', 'stat='], capture_output=True, text=True)
        return p.returncode == 0 and p.stdout.strip() and not p.stdout.strip().startswith('Z')

    def launch_args(self):
        return [sys.executable, '-u', str(SCRIPTS / 'launch.py'), '--root', str(self.root), '--binary', str(self.binary),
                '--gui-port', str(self.port), '--listen-port', '22000', '--no-discovery']

    def launch(self, close_lock=False):
        if close_lock:
            self.root.mkdir();(self.root / 'close-inherited-lock').touch()
        log = (self.base / 'launcher.log').open('w');self.addCleanup(log.close)
        p = subprocess.Popen(self.launch_args(), stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        self.children.append(p)
        state = self.root / '.launcher-state.json'
        for _ in range(100):
            if p.poll() is not None:
                self.fail((self.base / 'launcher.log').read_text())
            if state.exists():
                data = json.loads(state.read_text())
                if not close_lock or (self.root / 'close-inherited-lock').exists():
                    time.sleep(.15)
                    return p, data['child']['pid']
            time.sleep(.05)
        self.fail('No supervised child state')

    def assert_stopped(self, p, child):
        p.wait(timeout=15)
        for _ in range(30):
            if not self.running(child):return
            time.sleep(.1)
        self.fail('Child still alive')

    def test_sigterm_cleans_child(self):
        p, child = self.launch();p.terminate();self.assert_stopped(p, child)

    def test_stop_works_without_api_or_parseable_config(self):
        p, child = self.launch();(self.root / 'config.xml').write_text('BROKEN OFFLINE CONFIG')
        result = command('control.py', '--root', self.root, 'stop')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_stopped(p, child)

    def test_killed_parent_cannot_allow_second_launcher_to_rewrite(self):
        p, child = self.launch();before = (self.root / 'config.xml').read_bytes();p.kill();p.wait()
        self.assertTrue(self.running(child))
        retry = subprocess.run(self.launch_args(), capture_output=True, text=True, timeout=5)
        self.assertNotEqual(retry.returncode, 0)
        self.assertEqual((self.root / 'config.xml').read_bytes(), before)
        stopped = command('control.py', '--root', self.root, 'stop')
        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        self.assert_stopped(p, child)

    def test_existing_child_guard_also_works_if_child_closes_lock(self):
        p, child = self.launch(close_lock=True);before = (self.root / 'config.xml').read_bytes();p.kill();p.wait()
        retry = subprocess.run(self.launch_args(), capture_output=True, text=True, timeout=5)
        self.assertNotEqual(retry.returncode, 0)
        self.assertIn('existing Syncthing child', retry.stderr)
        self.assertEqual((self.root / 'config.xml').read_bytes(), before)
        result = command('control.py', '--root', self.root, 'stop')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_stopped(p, child)


if __name__ == '__main__':
    unittest.main()
