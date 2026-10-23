"""Cross-platform contracts; mocks are not evidence of native Windows operation."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch, Mock

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import platform_support as ps
import launch
import clash_rule
import control
import contextlib
import io


class PlatformContracts(unittest.TestCase):
    def test_download_selection_rejects_unknown_architecture(self):
        self.assertEqual(launch.download_platform('win32', 'AMD64'), ('windows', 'amd64'))
        self.assertEqual(launch.download_platform('win32', 'ARM64'), ('windows', 'arm64'))
        self.assertEqual(launch.download_platform('darwin', 'x86_64'), ('macos', 'amd64'))
        with self.assertRaises(ValueError):launch.download_platform('win32', 'x86')
        with self.assertRaises(ValueError):launch.download_platform('linux', 'amd64')

    def test_windows_lock_is_exclusive_and_child_handle_inherited(self):
        kernel = Mock();kernel.CreateFileW.return_value = 42
        startup = types.SimpleNamespace()
        with patch.object(ps, 'WINDOWS', True), patch.object(ps, '_kernel', return_value=kernel), patch.object(ps.os, 'set_handle_inheritable', create=True) as inherit, patch.object(ps.subprocess, 'STARTUPINFO', return_value=startup, create=True), patch.object(ps.subprocess, 'Popen') as popen:
            lock = ps.ProfileLock(Path('/synthetic/profile/.lock'))
            self.assertEqual(kernel.CreateFileW.call_args.args[2], 0)
            lock.spawn(['syncthing.exe', 'serve'])
            self.assertEqual(popen.call_args.kwargs['startupinfo'].lpAttributeList, {'handle_list': [42]})
            self.assertTrue(popen.call_args.kwargs['close_fds'])
            self.assertNotIn('pass_fds', popen.call_args.kwargs)
            self.assertEqual([x.args for x in inherit.call_args_list], [(42, True), (42, False)])
            lock.close();kernel.CloseHandle.assert_called_once_with(42)

    def test_windows_failed_spawn_resets_handle_inheritance(self):
        kernel = Mock();kernel.CreateFileW.return_value = 42
        with patch.object(ps, 'WINDOWS', True), patch.object(ps, '_kernel', return_value=kernel), patch.object(ps.os, 'set_handle_inheritable', create=True) as inherit, patch.object(ps.subprocess, 'STARTUPINFO', return_value=types.SimpleNamespace(), create=True), patch.object(ps.subprocess, 'Popen', side_effect=OSError('synthetic')):
            lock = ps.ProfileLock(Path('/synthetic/.lock'))
            with self.assertRaises(OSError):lock.spawn(['syncthing.exe'])
            self.assertEqual(inherit.call_args.args, (42, False));lock.close()

    def test_windows_pid_reuse_cannot_terminate_other_process(self):
        kernel = Mock()
        with patch.object(ps, 'WINDOWS', True), patch.object(ps, '_open_process', return_value=(kernel, 42)), patch.object(ps, '_started', return_value='new creation time'):
            with self.assertRaises(ValueError):ps.terminate_identity({'pid': 123, 'started': 'old creation time'})
            kernel.TerminateProcess.assert_not_called();kernel.CloseHandle.assert_called_once_with(42)

    def test_windows_stop_uses_validated_handle(self):
        kernel = Mock()
        with patch.object(ps, 'WINDOWS', True), patch.object(ps, '_open_process', return_value=(kernel, 42)), patch.object(ps, '_started', return_value='same'):
            ps.terminate_identity({'pid': 123, 'started': 'same'})
            kernel.TerminateProcess.assert_called_once_with(42, 1)

    def test_windows_process_rule_is_conditional_and_preserves_others(self):
        original = 'prepend:\n  - MATCH,PROXY\nappend: []\ndelete: []\n'
        result = clash_rule.revised(original, 'PROCESS-NAME,syncthing.exe,DIRECT')
        self.assertIn('  - PROCESS-NAME,syncthing.exe,DIRECT\n  - MATCH,PROXY', result)
        self.assertEqual(clash_rule.revised(result, 'PROCESS-NAME,syncthing.exe,DIRECT'), result)
        with self.assertRaises(ValueError):clash_rule.revised('prepend: []\ndelete:\n  - PROCESS-NAME,syncthing.exe,DIRECT\n', 'PROCESS-NAME,syncthing.exe,DIRECT')

    def test_windows_rule_moves_above_macos_rule_and_catchall(self):
        mac = 'PROCESS-NAME,syncthing,DIRECT'
        win = 'PROCESS-NAME,syncthing.exe,DIRECT'
        original = 'prepend:\n  - ' + mac + '\n  - MATCH,PROXY\n  - ' + win + '\nappend: []\ndelete: []\n'
        expected = 'prepend:\n  - ' + win + '\n  - ' + mac + '\n  - MATCH,PROXY\nappend: []\ndelete: []\n'
        result = clash_rule.revised(original, win)
        self.assertEqual(result, expected)
        self.assertEqual(clash_rule.revised(result, win), expected)


class WindowsStopContracts(unittest.TestCase):
    def test_stop_is_offline_scoped_child_first_and_handles_spaces(self):
        with tempfile.TemporaryDirectory(prefix='中文 root ') as folder:
            root = Path(folder).resolve()
            launcher = {'pid': 101, 'started': 'A', 'command': 'quoted launcher command', 'rootArgument': str(root), 'cwd': str(root)}
            child = {'pid': 102, 'started': 'B', 'command': 'quoted child command'}
            (root / '.launcher-state.json').write_text(json.dumps({'root': str(root), 'launcher': launcher, 'child': child}), encoding='utf-8')
            (root / 'config.xml').write_text('broken')
            live = {x['pid']: {k:x[k] for k in ('started','command')} for x in (launcher,child)}
            killed = []
            def terminate(item, force=False):killed.append(item['pid']);live.pop(item['pid'],None)
            def arguments(command):return ['python.exe','-u','C:/Tools/launch.py','--root',str(root)] if command==launcher['command'] else [str(root/'syncthing.exe'),'serve','--home',str(root)]
            with patch.object(control,'WINDOWS',True), patch.object(control,'binary_name',return_value='syncthing.exe'), patch.object(control,'windows_arguments',side_effect=arguments), patch.object(control,'process_identity',side_effect=lambda pid:live.get(pid)), patch.object(control,'terminate_identity',side_effect=terminate), contextlib.redirect_stdout(io.StringIO()):
                control.stop_profile(root)
            self.assertEqual(killed,[102,101])

    def test_mismatched_profile_argument_never_terminates(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();child={'pid':102,'started':'B','command':'wrong profile'}
            (root/'.launcher-state.json').write_text(json.dumps({'root':str(root),'child':child}), encoding='utf-8')
            with patch.object(control,'WINDOWS',True), patch.object(control,'binary_name',return_value='syncthing.exe'), patch.object(control,'windows_arguments',return_value=[str(root/'syncthing.exe'),'--home',str(root/'OTHER')]), patch.object(control,'process_identity',return_value={k:child[k] for k in ('started','command')}), patch.object(control,'terminate_identity') as stop:
                with self.assertRaises(ValueError):control.stop_profile(root)
                stop.assert_not_called()


@unittest.skipUnless(sys.platform == 'win32', 'Requires native Windows; not covered by mocked tests')
class NativeWindows(unittest.TestCase):
    def test_lock_remains_until_child_exit_and_identity_is_queryable(self):
        with tempfile.TemporaryDirectory(prefix='中文 profile ') as folder:
            path = Path(folder) / '.lock'
            lock = ps.ProfileLock(path)
            child = lock.spawn([sys.executable, '-c', 'import time; time.sleep(60)'])
            try:
                identity = ps.process_identity(child.pid)
                self.assertEqual(identity['pid'], child.pid)
                lock.close()
                with self.assertRaises(OSError):ps.ProfileLock(path)
                ps.terminate_identity(identity, force=True);child.wait(timeout=10)
                other = ps.ProfileLock(path);other.close()
            finally:
                if child.poll() is None:child.kill();child.wait()
                lock.close()


if __name__ == '__main__':unittest.main()
