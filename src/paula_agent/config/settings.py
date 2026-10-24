"""Settings read from environment variables (and `.env` in the working directory)."""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

from paula_agent.config.knowledge_folder import default_knowledge_dir


class SettingsError(Exception):
    pass


def _local_data() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PaulaPort"


def log_dir() -> Path:
    return _local_data() / "logs"


def setup_logging(level: str, name: str) -> None:
    """Log to a rotating file (pythonw at logon has no console) and to stderr if present."""
    log_dir().mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        RotatingFileHandler(
            log_dir() / f"{name}.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
    ]
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


@dataclass(frozen=True)
class Settings:
    rabbitmq_url: str
    agent_shared_secret: str
    elevenlabs_api_key: str
    elevenlabs_voice_id: str
    elevenlabs_model: str
    elevenlabs_speed: float
    mic_device: str
    speaker_device: str
    knowledge_dir: Path | None
    whisper_model: str
    whisper_language: str
    whisper_device: str
    wake_words: list[str]
    wake_word_min_confidence: float
    hotkey: str
    hotkey_listen_seconds: int
    conversation_seconds: float
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
            speed = float(os.environ.get("ELEVENLABS_SPEED") or 1.0)
            conversation_seconds = float(os.environ.get("CONVERSATION_SECONDS") or 8)
        except ValueError as exc:
            raise SettingsError(f"Invalid number in .env: {exc}") from exc
        if not 0 <= conversation_seconds <= 30:
            raise SettingsError("CONVERSATION_SECONDS must be between 0 (off) and 30")
        if not 0.7 <= speed <= 1.2:
            raise SettingsError("ELEVENLABS_SPEED must be between 0.7 and 1.2")
        whisper_device = (os.environ.get("WHISPER_DEVICE") or "auto").lower()
        if whisper_device not in ("auto", "cuda", "cpu"):
            raise SettingsError("WHISPER_DEVICE must be auto, cuda or cpu")
        knowledge_value = os.environ.get("KNOWLEDGE_DIR", "").strip()
        # "off" (as in the hub) means no knowledge base: the tab is hidden.
        knowledge_dir = (
            None
            if knowledge_value.lower() == "off"
            else Path(knowledge_value or default_knowledge_dir())
        )
        return cls(
            rabbitmq_url=os.environ.get("RABBITMQ_URL", "amqp://paula:paula@localhost:5672/"),
            agent_shared_secret=secret,
            elevenlabs_api_key=os.environ.get("ELEVENLABS_API_KEY", ""),
            elevenlabs_voice_id=os.environ.get("ELEVENLABS_VOICE_ID", "86V9x9hrQds83qf7zaGn"),
            elevenlabs_model=os.environ.get("ELEVENLABS_MODEL", "eleven_flash_v2_5"),
            elevenlabs_speed=speed,
            mic_device=os.environ.get("MIC_DEVICE", "").strip(),
            speaker_device=os.environ.get("SPEAKER_DEVICE", "").strip(),
            knowledge_dir=knowledge_dir,
            whisper_model=os.environ.get("WHISPER_MODEL", "small"),
            whisper_language=os.environ.get("WHISPER_LANGUAGE", "es"),
            whisper_device=whisper_device,
            wake_words=[
                w.strip() for w in os.environ.get("WAKE_WORDS", "paula,paula port").split(",")
            ],
            wake_word_min_confidence=min_confidence,
            hotkey=os.environ.get("HOTKEY", "ctrl+shift+p"),
            hotkey_listen_seconds=listen_seconds,
            conversation_seconds=conversation_seconds,
            excluded_apps=os.environ.get("EXCLUDED_APPS", ""),
            apps_file=Path(apps_file) if apps_file else None,
            models_dir=Path(os.environ.get("MODELS_DIR") or _local_data() / "models"),
            env_file=env_file,
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )
