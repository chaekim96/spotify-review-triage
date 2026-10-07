"""Atomic file writes: write a temp file in the same directory, fsync, then os.replace."""

import json
import os
import tempfile
from pathlib import Path


def atomic_write_bytes(path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix="." + path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def atomic_write_text(path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def json_text(value) -> str:
    """Same layout as the vendored checker's write_json, so files are byte-comparable."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def atomic_write_json(path, value) -> None:
    atomic_write_text(path, json_text(value))
