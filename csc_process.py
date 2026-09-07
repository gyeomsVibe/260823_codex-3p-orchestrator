"""Non-destructive process observation shared by all CSC adapters."""

import os
import sys


def probe_pid(pid: int) -> str:
    """Return alive, gone or unknown; never send a signal on Windows."""
    if type(pid) is not int or pid <= 0:
        return "gone"
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        # SYNCHRONIZE gives observation rights only, never termination rights.
        handle = kernel.OpenProcess(0x00100000, False, pid)
        if not handle:
            return "gone" if ctypes.get_last_error() == 87 else "unknown"
        try:
            result = kernel.WaitForSingleObject(handle, 0)
            return {0: "gone", 258: "alive"}.get(result, "unknown")
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return "alive"
    except ProcessLookupError:
        return "gone"
    except PermissionError:
        return "unknown"
    except OSError:
        return "unknown"
