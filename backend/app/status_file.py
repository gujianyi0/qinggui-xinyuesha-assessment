"""Resilient atomic writes for local preview state/diagnostic files.

On Windows, ``Path.replace`` over a file another process is reading can fail
transiently with ``PermissionError`` (WinError 5). The supervisor previously let
that exception escape from ``report()``, so a diagnostic-file race took down the
web/API/Worker/PostgreSQL/Kafka group. Status files are observability, not a
liveness dependency: a failed write must never stop the preview.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

# Short, bounded retries: enough to ride out an antivirus/indexer handle, never
# long enough to stall the supervisor's 0.5s loop.
REPLACE_ATTEMPTS = 6
REPLACE_DELAY_SECONDS = 0.05


def atomic_write_text(path: Path, text: str, *, attempts: int = REPLACE_ATTEMPTS,
                      delay: float = REPLACE_DELAY_SECONDS) -> bool:
    """Write *text* to *path* atomically; return False instead of raising.

    Each attempt uses its own temporary file so concurrent writers cannot
    clobber one another. A persistent failure leaves the previous file intact
    and is reported by the caller's diagnostic channel.
    """
    temporary = path.with_name(f"{path.name}.{os.getpid()}.{time.monotonic_ns()}.tmp")
    try:
        for attempt in range(attempts):
            try:
                temporary.write_text(text, encoding="utf-8")
                os.replace(temporary, path)
                return True
            except OSError:
                if attempt + 1 < attempts:
                    time.sleep(delay)
        return False
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def atomic_write_json(path: Path, value: object, **kwargs: object) -> bool:
    """JSON variant of :func:`atomic_write_text`."""
    return atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n", **kwargs)
