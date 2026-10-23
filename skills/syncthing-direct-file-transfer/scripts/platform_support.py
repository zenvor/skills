"""Platform-specific profile locks and process identity; no global process matching."""
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys

WINDOWS = sys.platform == 'win32'


def binary_name():
    return 'syncthing.exe' if WINDOWS else 'syncthing'


def _kernel():
    from ctypes import wintypes as w
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    signatures = {
        'CreateFileW': ([w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE], w.HANDLE),
        'CloseHandle': ([w.HANDLE], w.BOOL),
        'OpenProcess': ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
        'GetProcessTimes': ([w.HANDLE] + [ctypes.POINTER(w.FILETIME)] * 4, w.BOOL),
        'GetExitCodeProcess': ([w.HANDLE, ctypes.POINTER(w.DWORD)], w.BOOL),
        'TerminateProcess': ([w.HANDLE, w.UINT], w.BOOL),
    }
    for name, (args, result) in signatures.items():
        f = getattr(k, name);f.argtypes = args;f.restype = result
    return k


def _started(k, handle):
    from ctypes import wintypes as w
    stamps = [w.FILETIME() for _ in range(4)]
    if not k.GetProcessTimes(handle, *[ctypes.byref(x) for x in stamps]):
        raise ctypes.WinError(ctypes.get_last_error())
    return str((stamps[0].dwHighDateTime << 32) | stamps[0].dwLowDateTime)


def _open_process(pid, access):
    k = _kernel();h = k.OpenProcess(access, False, int(pid))
    if not h:
        error = ctypes.get_last_error()
        if error == 87:  # PID no longer exists
            return k, None
        raise ctypes.WinError(error)  # Access denied is unknown, never proof of exit.
    return k, h


def process_identity(pid):
    if not WINDOWS:
        values = []
        for field in ['lstart=', 'args=']:
            r = subprocess.run(['ps', '-p', str(pid), '-o', field], capture_output=True, text=True,
                               env={**os.environ, 'LC_ALL': 'C'})
            if r.returncode or not r.stdout.strip():return None
            values.append(r.stdout.strip())
        return {'pid': pid, 'started': values[0], 'command': values[1]}
    from ctypes import wintypes as w
    k, h = _open_process(pid, 0x1000)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:return None
    try:
        code = w.DWORD()
        if not k.GetExitCodeProcess(h, ctypes.byref(code)):raise ctypes.WinError(ctypes.get_last_error())
        if code.value != 259:return None
        started = _started(k, h)
        # Integer-only PID interpolation; no profile path or user text enters PowerShell code.
        ps = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        query = '[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); (Get-CimInstance Win32_Process -Filter "ProcessId = %d" -ErrorAction Stop).CommandLine | ConvertTo-Json -Compress' % int(pid)
        r = subprocess.run([str(ps), '-NoProfile', '-NonInteractive', '-Command', query],
                           capture_output=True, text=True, encoding='utf-8-sig', timeout=15)
        if r.returncode:raise RuntimeError('Cannot query Windows command line; process ownership unknown')
        command = json.loads(r.stdout)
        if not k.GetExitCodeProcess(h, ctypes.byref(code)):raise ctypes.WinError(ctypes.get_last_error())
        if code.value != 259:return None
        if not isinstance(command, str) or not command:raise RuntimeError('Windows command line unavailable')
        # Recheck after CIM lookup to avoid attaching metadata from a reused PID.
        if _started(k, h) != started:raise RuntimeError('Process identity changed')
        return {'pid': pid, 'started': started, 'command': command}
    finally:
        k.CloseHandle(h)


def terminate_identity(identity, force=False):
    """Windows validates creation time on the same handle used for termination."""
    if not WINDOWS:
        import signal
        current = process_identity(identity['pid'])
        if current and all(current[k] == identity[k] for k in ('started', 'command')):
            os.kill(identity['pid'], signal.SIGKILL if force else signal.SIGTERM)
        return
    k, h = _open_process(identity['pid'], 0x1001)
    if not h:return
    try:
        if _started(k, h) != identity['started']:raise ValueError('PID reused; no termination sent')
        if not k.TerminateProcess(h, 1):raise ctypes.WinError(ctypes.get_last_error())
    finally:k.CloseHandle(h)


def windows_arguments(command):
    from ctypes import wintypes as w
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    shell.CommandLineToArgvW.argtypes = [w.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(w.LPWSTR)
    count = ctypes.c_int();argv = shell.CommandLineToArgvW(command, ctypes.byref(count))
    if not argv:raise ctypes.WinError(ctypes.get_last_error())
    try:return [argv[i] for i in range(count.value)]
    finally:
        k = ctypes.WinDLL('kernel32', use_last_error=True)
        k.LocalFree.argtypes = [ctypes.c_void_p];k.LocalFree.restype = ctypes.c_void_p
        k.LocalFree(argv)


class ProfileLock:
    """Child retains the lock after a forced parent exit on either platform."""
    def __init__(self, path):
        self.stream = None;self.handle = None
        if WINDOWS:
            k = _kernel()
            # shareMode=0 denies concurrent opens, including other launcher processes.
            h = k.CreateFileW(str(path), 0xC0000000, 0, None, 4, 0x80, None)
            if h == ctypes.c_void_p(-1).value:
                raise OSError('Profile is locked or inaccessible; no configuration changed')
            self.handle = h
        else:
            import fcntl
            self.stream = path.open('a')
            try:fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BaseException:self.stream.close();raise

    def spawn(self, args, **kwargs):
        if not WINDOWS:
            return subprocess.Popen(args, pass_fds=(self.stream.fileno(),), **kwargs)
        startup = subprocess.STARTUPINFO()
        os.set_handle_inheritable(self.handle, True)
        startup.lpAttributeList = {'handle_list': [self.handle]}
        try:return subprocess.Popen(args, startupinfo=startup, close_fds=True, **kwargs)
        finally:os.set_handle_inheritable(self.handle, False)

    def close(self):
        if self.stream:self.stream.close();self.stream = None
        if self.handle:_kernel().CloseHandle(self.handle);self.handle = None

    def __del__(self):
        self.close()
