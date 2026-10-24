"""Read and delete Paula's long-term memory from the settings window.

The hub owns the memory (`memory.sqlite3` in %LOCALAPPDATA%\\PaulaPort). In v1 hub and
agent run on the same PC, so the window opens that file directly instead of adding
messages to the contract. Only reading and deleting happen here; saving stays in the hub.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Fact:
    id: str
    text: str


class MemoryFile:
    def __init__(self, path: Path) -> None:
        self._path = path

    def facts(self) -> list[Fact]:
        if not self._path.exists():
            return []
        with closing(self._connect()) as db:
            try:
                rows = db.execute("SELECT id, text FROM facts ORDER BY created_at").fetchall()
            except sqlite3.OperationalError:
                return []  # the hub has not created the table yet
        return [Fact(*row) for row in rows]

    def delete(self, ids: list[str]) -> None:
        if not ids or not self._path.exists():
            return
        with closing(self._connect()) as db, db:
            db.executemany("DELETE FROM facts WHERE id = ?", [(i,) for i in ids])

    def _connect(self) -> sqlite3.Connection:
        # The hub may be writing at the same time: wait for its lock instead of failing.
        return sqlite3.connect(str(self._path), timeout=5)
