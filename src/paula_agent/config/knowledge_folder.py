"""The folder of documents Paula learns from (the hub indexes it every minute).

The window only copies files in, lists them and removes them; reading and indexing
happen in the hub, so the two sides share nothing but the folder.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

SUFFIXES = (".md", ".txt", ".pdf")
# Same limits as the hub (adapters/outbound/memory/knowledge.py): larger files are
# never learned, so they are not copied either.
MAX_FILE_BYTES = 20_000_000
MAX_DEPTH = 8


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
        found = []
        for root, dirs, names in os.walk(self.path):
            here = Path(root)
            depth = len(here.relative_to(self.path).parts)
            # Like the hub: never follow junctions or symlinks, nor go too deep.
            dirs[:] = [
                d
                for d in dirs
                if depth < MAX_DEPTH
                and not (here / d).is_symlink()
                and not (here / d).is_junction()
            ]
            found += [
                (here / n).relative_to(self.path).as_posix()
                for n in names
                if Path(n).suffix.lower() in SUFFIXES
            ]
        return sorted(found)

    def add(self, sources: list[Path]) -> tuple[list[str], list[str]]:
        """Copy files in; returns (added names, skipped names with the reason)."""
        self.path.mkdir(parents=True, exist_ok=True)
        added, skipped = [], []
        for source in sources:
            if source.suffix.lower() not in SUFFIXES or not source.is_file():
                skipped.append(f"{source.name} (formato no soportado)")
                continue
            if source.stat().st_size > MAX_FILE_BYTES:
                skipped.append(f"{source.name} (más de 20 MB)")
                continue
            added.append(self._copy(source))
        return added, skipped

    def _copy(self, source: Path) -> str:
        # Copy under a temporary name first: the hub must never index half a file.
        partial = self.path / f"{source.name}.partial"
        try:
            shutil.copyfile(source, partial)
            n = 2
            target = self.path / source.name
            while True:
                try:
                    # A hard link fails if the name exists, so nothing is ever overwritten,
                    # even if a file with that name appeared during the copy.
                    os.link(partial, target)
                    return target.name
                except FileExistsError:
                    target = self.path / f"{source.stem} ({n}){source.suffix}"
                    n += 1
        finally:
            partial.unlink(missing_ok=True)

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
