"""Settings read from environment variables (and `.env` in the working directory)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class SettingsError(Exception):
    pass


def _local_data() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PaulaPort"


@dataclass(frozen=True)
class Settings:
    rabbitmq_url: str
    agent_shared_secret: str
    elevenlabs_api_key: str
    elevenlabs_voice_id: str
    elevenlabs_model: str
    whisper_model: str
    whisper_language: str
    wake_words: list[str]
    wake_word_min_confidence: float
    hotkey: str
    hotkey_listen_seconds: int
    excluded_apps: str
    apps_file: Path | None
    models_dir: Path
    env_file: Path
    log_level: str

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> Settings:
        env_file = env_file or Path.cwd() / ".env"
        load_dotenv(env_file)
        secret = os.environ.get("AGENT_SHARED_SECRET", "")
        if len(secret) < 32:
            raise SettingsError("AGENT_SHARED_SECRET must be at least 32 characters")
        apps_file = os.environ.get("APPS_FILE")
        try:
            min_confidence = float(os.environ.get("WAKE_WORD_MIN_CONFIDENCE") or 0.85)
            listen_seconds = int(os.environ.get("HOTKEY_LISTEN_SECONDS") or 5)
        except ValueError as exc:
            raise SettingsError(f"Invalid number in .env: {exc}") from exc
        return cls(
            rabbitmq_url=os.environ.get("RABBITMQ_URL", "amqp://paula:paula@localhost:5672/"),
            agent_shared_secret=secret,
            elevenlabs_api_key=os.environ.get("ELEVENLABS_API_KEY", ""),
            elevenlabs_voice_id=os.environ.get("ELEVENLABS_VOICE_ID", "86V9x9hrQds83qf7zaGn"),
            elevenlabs_model=os.environ.get("ELEVENLABS_MODEL", "eleven_flash_v2_5"),
            whisper_model=os.environ.get("WHISPER_MODEL", "small"),
            whisper_language=os.environ.get("WHISPER_LANGUAGE", "es"),
            wake_words=[
                w.strip() for w in os.environ.get("WAKE_WORDS", "paula,paula port").split(",")
            ],
            wake_word_min_confidence=min_confidence,
            hotkey=os.environ.get("HOTKEY", "ctrl+shift+p"),
            hotkey_listen_seconds=listen_seconds,
            excluded_apps=os.environ.get("EXCLUDED_APPS", ""),
            apps_file=Path(apps_file) if apps_file else None,
            models_dir=Path(os.environ.get("MODELS_DIR") or _local_data() / "models"),
            env_file=env_file,
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )
