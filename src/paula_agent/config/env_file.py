"""Change values in `.env` without touching the rest of the file (comments, secrets)."""

from __future__ import annotations

import os
import re
from pathlib import Path

_LINE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=")


def update_env(path: Path, values: dict[str, str]) -> None:
    for key, value in values.items():
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise ValueError(f"Invalid setting name: {key}")
        if "\n" in value or "\r" in value:
            raise ValueError(f"{key} cannot contain line breaks")

    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    pending = dict(values)
    for i, line in enumerate(lines):
        match = _LINE.match(line)
        if match and match.group(1) in pending:
            key = match.group(1)
            lines[i] = f"{key}={pending.pop(key)}"
    lines.extend(f"{key}={value}" for key, value in pending.items())

    # Write next to the file and swap, so a crash never leaves a half-written .env.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, path)
