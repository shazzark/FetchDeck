from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import Sequence


class RecycleBinError(OSError):
    """A requested move to the Windows Recycle Bin could not be completed."""


def move_to_recycle_bin(paths: Sequence[Path]) -> None:
    """Move files to the Windows Recycle Bin and report shell-operation errors."""
    existing = [path for path in paths if path.exists()]
    if not existing:
        raise RecycleBinError("No downloaded files were found to move to the Recycle Bin.")
    if os.name != "nt":
        raise RecycleBinError("Moving downloads to the Recycle Bin is supported on Windows only.")

    class FileOperation(ctypes.Structure):
        _fields_ = [
            ("hwnd", ctypes.c_void_p),
            ("wFunc", ctypes.c_uint),
            ("pFrom", ctypes.c_wchar_p),
            ("pTo", ctypes.c_wchar_p),
            ("fFlags", ctypes.c_ushort),
            ("fAnyOperationsAborted", ctypes.c_int),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", ctypes.c_wchar_p),
        ]

    source_list = "\0".join(str(path) for path in existing) + "\0\0"
    operation = FileOperation()
    operation.wFunc = 3  # FO_DELETE
    operation.pFrom = source_list
    operation.fFlags = 0x0040  # FOF_ALLOWUNDO sends deleted files to the Recycle Bin.
    try:
        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    except (OSError, ctypes.ArgumentError) as exc:
        raise RecycleBinError("Windows could not start the Recycle Bin operation.") from exc
    if result or operation.fAnyOperationsAborted:
        raise RecycleBinError(f"Windows could not move the download to the Recycle Bin (code {result}).")
