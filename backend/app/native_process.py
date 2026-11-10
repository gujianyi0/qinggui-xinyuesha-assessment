"""Process helpers shared by local verification scripts and the native demo."""
import ctypes
import os
import re
import subprocess
from ctypes import wintypes
from pathlib import Path


class WindowsJob:
    """Kill this owned process tree when the owner dies or explicitly closes it."""
    def __init__(self):
        self.handle = None
        if os.name != "nt":
            return
        class Basic(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64), ("flags", wintypes.DWORD),
                        ("min_ws", ctypes.c_size_t), ("max_ws", ctypes.c_size_t), ("active", wintypes.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(key, ctypes.c_uint64) for key in ("read_ops", "write_ops", "other_ops", "read", "write", "other")]
        class Extended(ctypes.Structure):
            _fields_ = [("basic", Basic), ("io", IO), ("process_limit", ctypes.c_size_t), ("job_limit", ctypes.c_size_t),
                        ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes, self.kernel.CreateJobObjectW.restype = [ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE
        self.kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
        self.kernel.OpenProcess.argtypes, self.kernel.OpenProcess.restype = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        limits = Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.handle or not self.kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())

    def assign(self, pid):
        if self.handle is None:
            return
        process = self.kernel.OpenProcess(0x100 | 0x1, False, pid)
        if not process:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            contained = wintypes.BOOL()
            if self.kernel.IsProcessInJob(process, self.handle, ctypes.byref(contained)) and contained.value:
                return
            if not self.kernel.AssignProcessToJobObject(self.handle, process):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            self.kernel.CloseHandle(process)

    def close(self):
        if self.handle is not None:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def java_executable(candidate):
    if not candidate:
        raise ValueError("Java 17+ is required")
    result = subprocess.run([str(candidate), "-XshowSettings:properties", "-version"], capture_output=True, timeout=15)
    properties = (result.stdout + result.stderr).decode(errors="replace")
    match = re.search(r"^\s*java.home\s*=\s*(.+)$", properties, re.MULTILINE)
    if match:
        executable = Path(match[1].strip()) / "bin" / ("java.exe" if os.name == "nt" else "java")
        if executable.is_file():
            return executable
    raise ValueError("Cannot locate the real Java executable")


def stop_owned(process):
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
