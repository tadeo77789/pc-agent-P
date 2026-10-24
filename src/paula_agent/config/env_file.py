"""Change values in `.env` without touching the rest of the file (comments, secrets)."""

from __future__ import annotations

import os
import re
from pathlib import Path

_LINE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=")


def _line(key: str, value: str) -> str:
    # Single quotes: python-dotenv takes the value literally (no "#" comments, no ${VAR}
    # expansion); only backslash and the quote itself need escaping.
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"{key}='{escaped}'"


def update_env(path: Path, values: dict[str, str]) -> None:
    for key, value in values.items():
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
            raise ValueError(f"Invalid setting name: {key}")
        # Any line separator (\n, \r,  ...) would let a value start a new key line.
        if len(f"x{value}x".splitlines()) != 1:
            raise ValueError(f"{key} cannot contain line breaks")
        if "${" in value:  # python-dotenv expands ${VAR} even inside quotes
            raise ValueError(f"{key} cannot contain ${{")

    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    pending = dict(values)
    for i, line in enumerate(lines):
        match = _LINE.match(line)
        if match and match.group(1) in pending:
            key = match.group(1)
            lines[i] = _line(key, pending.pop(key))
    lines.extend(_line(key, value) for key, value in pending.items())

    # Write next to the file and swap, so a crash never leaves a half-written .env.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(tmp, path)
