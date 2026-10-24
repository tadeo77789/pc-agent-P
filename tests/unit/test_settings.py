from pathlib import Path

import pytest

from paula_agent.config.settings import Settings, SettingsError

NAMES = ("AGENT_SHARED_SECRET", "WAKE_WORDS", "ELEVENLABS_API_KEY", "APPS_FILE", "MODELS_DIR")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in NAMES:
        monkeypatch.delenv(name, raising=False)


def test_short_secret_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_SHARED_SECRET", "short")

    with pytest.raises(SettingsError):
        Settings.from_env(tmp_path / ".env")


def test_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_SHARED_SECRET", "x" * 32)

    settings = Settings.from_env(tmp_path / ".env")

    assert settings.wake_words == ["paula", "paula port"]
    assert settings.elevenlabs_model == "eleven_flash_v2_5"
    assert settings.hotkey == "ctrl+shift+p"
    assert settings.apps_file is None
    assert settings.env_file == tmp_path / ".env"


def test_env_file_is_read(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text(f"AGENT_SHARED_SECRET={'y' * 40}\nWAKE_WORDS=paula\nAPPS_FILE=apps.json\n")

    settings = Settings.from_env(env)

    assert settings.wake_words == ["paula"]
    assert settings.apps_file == Path("apps.json")


def test_empty_optional_paths_use_defaults(monkeypatch, tmp_path):
    env = tmp_path / ".env"
    env.write_text(f"AGENT_SHARED_SECRET={'y' * 40}\nAPPS_FILE=\nMODELS_DIR=\n")

    settings = Settings.from_env(env)

    assert settings.apps_file is None
    assert settings.models_dir.name == "models"


def test_invalid_number_is_a_settings_error(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_SHARED_SECRET", "x" * 32)
    monkeypatch.setenv("HOTKEY_LISTEN_SECONDS", "cinco")

    with pytest.raises(SettingsError):
        Settings.from_env(tmp_path / ".env")
