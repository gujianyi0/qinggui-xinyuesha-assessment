"""Small process/commit samples without importing a model or a monitoring agent."""
import ctypes
import os
from ctypes import wintypes
from functools import cache


class Entry(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("usage", wintypes.DWORD), ("pid", wintypes.DWORD),
                ("heap", ctypes.c_size_t), ("module", wintypes.DWORD), ("threads", wintypes.DWORD),
                ("parent", wintypes.DWORD), ("priority", wintypes.LONG), ("flags", wintypes.DWORD),
                ("exe", wintypes.WCHAR * 260)]


class Counters(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
        (key, ctypes.c_size_t) for key in ("peak_rss", "rss", "peak_paged", "paged", "peak_nonpaged",
                                         "nonpaged", "pagefile", "peak_pagefile", "private")]


class Memory(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("load", wintypes.DWORD)] + [
        (key, ctypes.c_ulonglong) for key in ("total", "free", "commit_limit", "commit_free", "virtual", "virtual_free", "extended")]


@cache
def apis():
    kernel, psapi = ctypes.WinDLL("kernel32", use_last_error=True), ctypes.WinDLL("psapi", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.OpenProcess.argtypes, kernel.OpenProcess.restype = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    kernel.GetProcessHandleCount.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    return kernel, psapi


def windows_processes() -> list[dict]:
    if os.name != "nt":
        return []

    kernel, _ = apis()
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    rows = []
    try:
        entry = Entry()
        entry.size = ctypes.sizeof(entry)
        valid = kernel.Process32FirstW(handle, ctypes.byref(entry))
        while valid:
            rows.append({"pid": entry.pid, "parent_pid": entry.parent, "name": entry.exe})
            valid = kernel.Process32NextW(handle, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(handle)
    return rows


def process_memory(pid: int | None = None) -> dict:
    pid = pid or os.getpid()
    if os.name != "nt":
        return {"pid": pid, "available": False}

    kernel, psapi = apis()
    handle = kernel.OpenProcess(0x1000 | 0x10, False, pid)
    if not handle:
        return {"pid": pid, "available": False}
    try:
        counts, handles = Counters(), wintypes.DWORD()
        counts.size = ctypes.sizeof(counts)
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counts), counts.size):
            return {"pid": pid, "available": False}
        kernel.GetProcessHandleCount(handle, ctypes.byref(handles))
        return {"pid": pid, "available": True, "private_bytes": counts.private,
                "working_set_bytes": counts.rss, "peak_working_set_bytes": counts.peak_rss, "handles": handles.value}
    finally:
        kernel.CloseHandle(handle)


def process_tree(pid: int, entries: list[dict] | None = None) -> list[dict]:
    entries = windows_processes() if entries is None else entries
    children, pending = {pid}, [pid]
    while pending:
        parent = pending.pop()
        for item in entries:
            if item["parent_pid"] == parent and item["pid"] not in children:
                children.add(item["pid"])
                pending.append(item["pid"])
    return [process_memory(item) for item in sorted(children)]


def system_memory() -> dict:
    if os.name != "nt":
        return {"available": False}

    value = Memory()
    value.size = ctypes.sizeof(value)
    kernel, _ = apis()
    if not kernel.GlobalMemoryStatusEx(ctypes.byref(value)):
        return {"available": False}
    return {"available": True, "physical_load_percent": value.load, "physical_total_bytes": value.total,
            "physical_free_bytes": value.free, "commit_limit_bytes": value.commit_limit, "commit_free_bytes": value.commit_free}
