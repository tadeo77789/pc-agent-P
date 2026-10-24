from pathlib import Path

import pytest

from paula_agent.config.knowledge_folder import KnowledgeFolder


@pytest.fixture
def folder(tmp_path):
    return KnowledgeFolder(tmp_path / "Conocimiento")


def source(tmp_path, name, text="contenido"):
    path = tmp_path / "descargas" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_add_copies_supported_files_without_overwriting(folder, tmp_path):
    first = source(tmp_path, "guia.md", "uno")

    folder.add([first])
    added, skipped = folder.add([source(tmp_path, "guia.md", "dos"), source(tmp_path, "foto.png")])

    assert added == ["guia (2).md"]
    assert skipped == ["foto.png (formato no soportado)"]
    assert folder.files() == ["guia (2).md", "guia.md"]
    assert (folder.path / "guia.md").read_text(encoding="utf-8") == "uno"
    assert not list(folder.path.glob("*.partial"))


def test_lists_subfolders_and_ignores_other_files(folder):
    (folder.path / "notas de Paula").mkdir(parents=True)
    (folder.path / "notas de Paula" / "a.md").write_text("x", encoding="utf-8")
    (folder.path / "LEEME.txt").write_text("x", encoding="utf-8")
    (folder.path / "foto.png").write_bytes(b"x")

    assert folder.files() == ["LEEME.txt", "notas de Paula/a.md"]


def test_remove_only_inside_the_folder(folder, tmp_path):
    folder.add([source(tmp_path, "guia.md")])
    outside = source(tmp_path, "secreto.txt")

    with pytest.raises(ValueError):
        folder.remove(["../descargas/secreto.txt"])
    folder.remove(["guia.md"])

    assert folder.files() == []
    assert outside.exists()


def test_missing_folder_lists_nothing(folder):
    assert folder.files() == []


def test_files_over_the_hub_limit_are_skipped(folder, tmp_path, monkeypatch):
    import paula_agent.config.knowledge_folder as module

    monkeypatch.setattr(module, "MAX_FILE_BYTES", 5)
    added, skipped = folder.add([source(tmp_path, "grande.pdf", "mas de cinco")])

    assert added == []
    assert skipped == ["grande.pdf (más de 20 MB)"]


def test_failed_copy_leaves_no_partial_file(folder, tmp_path, monkeypatch):
    import paula_agent.config.knowledge_folder as module

    def broken(src, dst):
        Path(dst).write_text("medio", encoding="utf-8")
        raise OSError("disk full")

    monkeypatch.setattr(module.shutil, "copyfile", broken)

    with pytest.raises(OSError):
        folder.add([source(tmp_path, "guia.md")])

    assert list(folder.path.iterdir()) == []
