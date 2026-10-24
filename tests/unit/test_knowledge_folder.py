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
    assert skipped == ["foto.png"]
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
