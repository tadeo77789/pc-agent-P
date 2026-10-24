import sqlite3
from typing import ClassVar

import pytest

from paula_agent.audio.devices import AudioDevice
from paula_agent.config.memory_file import MemoryFile
from paula_agent.config.settings import Settings
from paula_agent.ui.settings.window import SettingsWindow

DEVICES = {
    "input": [
        AudioDevice(1, "Micrófono (Realtek)", True),
        AudioDevice(2, "Micrófono (USB)", False),
    ],
    "output": [AudioDevice(4, "Auriculares", True), AudioDevice(5, "Altavoces", False)],
}


class FakeMeter:
    opened: ClassVar[list] = []

    def __init__(self, device):
        FakeMeter.opened.append(device)
        self.level = 0.5
        self.closed = False

    def close(self):
        self.closed = True


@pytest.fixture
def env(tmp_path, monkeypatch):
    for name in ("MIC_DEVICE", "SPEAKER_DEVICE", "ELEVENLABS_SPEED", "CONVERSATION_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AGENT_SHARED_SECRET", "x" * 32)
    path = tmp_path / ".env"
    path.write_text("AGENT_SHARED_SECRET=" + "x" * 32 + "\nMIC_DEVICE=Micrófono (USB)\n", "utf-8")
    return path


def memory_db(tmp_path, facts):
    path = tmp_path / "memory.sqlite3"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE facts (id TEXT, text TEXT, embedding BLOB, created_at TEXT)")
    db.executemany("INSERT INTO facts VALUES (?, ?, x'', ?)", facts)
    db.commit()
    db.close()
    return MemoryFile(path)


def make(env, tmp_path, memory=None):
    FakeMeter.opened = []
    return SettingsWindow(
        Settings.from_env(env),
        list_devices=lambda kind: DEVICES[kind],
        memory=memory or MemoryFile(tmp_path / "none.sqlite3"),
        open_meter=FakeMeter,
        play_tone=lambda device: None,
    )


def test_shows_saved_mic_and_default_speaker(qapp, env, tmp_path):
    window = make(env, tmp_path)

    assert window.mic.currentText() == "Micrófono (USB)"
    assert window.speaker.currentText() == "Predeterminado de Windows (Auriculares)"


def test_save_writes_env_and_signals_restart(qapp, env, tmp_path):
    window = make(env, tmp_path)
    saved = []
    window.saved.connect(lambda: saved.append(True))
    window.speaker.setCurrentIndex(window.speaker.findText("Altavoces"))
    window.conversation.setValue(12)
    window.excluded.setText(" Discord.exe ,, PioneerGame.exe ")

    window.save()

    text = env.read_text("utf-8")
    assert "AGENT_SHARED_SECRET=" + "x" * 32 in text  # untouched
    assert "MIC_DEVICE=Micrófono (USB)" in text
    assert "SPEAKER_DEVICE=Altavoces" in text
    assert "CONVERSATION_SECONDS=12" in text
    assert "EXCLUDED_APPS=discord.exe,pioneergame.exe" in text
    assert saved == [True]


def test_unplugged_mic_is_kept_when_saving(qapp, env, tmp_path):
    env.write_text(env.read_text("utf-8").replace("Micrófono (USB)", "Headset viejo"), "utf-8")
    window = make(env, tmp_path)

    assert window.mic.currentText() == "Headset viejo (no conectado)"
    assert window.changes()["MIC_DEVICE"] == "Headset viejo"


def test_level_meter_follows_the_chosen_mic_and_closes(qapp, env, tmp_path):
    window = make(env, tmp_path)
    window.show()
    assert FakeMeter.opened == [2]

    window.mic.setCurrentIndex(0)  # Windows default
    window._update_meter()

    assert FakeMeter.opened == [2, None]
    assert window.level.value() == 50
    window.close()
    assert window._meter is None


def test_memory_tab_lists_and_deletes_facts(qapp, env, tmp_path):
    memory = memory_db(
        tmp_path, [("a", "A Ola le gusta el rock", "1"), ("b", "Ola tiene un perro", "2")]
    )
    window = make(env, tmp_path, memory)

    assert [window.facts.item(i).text() for i in range(window.facts.count())] == [
        "A Ola le gusta el rock",
        "Ola tiene un perro",
    ]
    window.facts.item(0).setSelected(True)
    window._delete_selected()

    assert [f.text for f in memory.facts()] == ["Ola tiene un perro"]


def test_empty_memory_shows_a_hint(qapp, env, tmp_path):
    window = make(env, tmp_path)

    assert window.facts.item(0).text() == "Paula todavía no recuerda nada."
