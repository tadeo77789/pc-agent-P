"""The folder of documents Paula learns from (the hub indexes it every minute).

The window only copies files in, lists them and removes them; reading and indexing
happen in the hub, so the two sides share nothing but the folder.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

SUFFIXES = (".md", ".txt", ".pdf")


def default_knowledge_dir() -> Path:
    """Documents\\Paula\\Conocimiento, the same default as the hub."""
    return (
        Path(os.environ.get("USERPROFILE") or Path.home()) / "Documents" / "Paula" / "Conocimiento"
    )


class KnowledgeFolder:
    def __init__(self, path: Path) -> None:
        self.path = path

    def files(self) -> list[str]:
        if not self.path.is_dir():
            return []
        return sorted(
            p.relative_to(self.path).as_posix()
            for p in self.path.rglob("*")
            if p.is_file() and p.suffix.lower() in SUFFIXES
        )

    def add(self, sources: list[Path]) -> tuple[list[str], list[str]]:
        """Copy files in; returns (added names, skipped names)."""
        self.path.mkdir(parents=True, exist_ok=True)
        added, skipped = [], []
        for source in sources:
            if source.suffix.lower() not in SUFFIXES or not source.is_file():
                skipped.append(source.name)
                continue
            target = self.path / source.name
            n = 2
            while target.exists():  # never overwrite a document already there
                target = self.path / f"{source.stem} ({n}){source.suffix}"
                n += 1
            # Copy under a temporary name first: the hub must never index half a file.
            partial = target.with_name(target.name + ".partial")
            shutil.copyfile(source, partial)
            os.replace(partial, target)
            added.append(target.name)
        return added, skipped

    def remove(self, names: list[str]) -> None:
        root = self.path.resolve()
        for name in names:
            target = (self.path / name).resolve()
            if root not in target.parents:  # only files inside the folder
                raise ValueError(f"{name} is not in the knowledge folder")
            target.unlink(missing_ok=True)

    def open_in_explorer(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        os.startfile(self.path)  # a folder: Windows opens it in Explorer
