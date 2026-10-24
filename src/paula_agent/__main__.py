"""Run the agent: python -m paula_agent"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading

from PySide6.QtWidgets import QApplication

from paula_agent.activation.foreground import ExclusionPolicy, foreground_window
from paula_agent.activation.hotkey import HotkeyListener
from paula_agent.activation.wake_word import WakeWordDetector, ensure_model
from paula_agent.audio.devices import list_devices, resolve
from paula_agent.audio.recorder import Recorder
from paula_agent.audio.stt import Transcriber
from paula_agent.audio.tts import SoundDevicePlayer, Speaker
from paula_agent.commands.runner import CommandRunner, load_apps
from paula_agent.config.memory_file import MemoryFile
from paula_agent.config.settings import Settings, SettingsError, log_dir, setup_logging
from paula_agent.controller import AgentController
from paula_agent.messaging.bus import AgentBus
from paula_agent.ui.settings.window import SettingsWindow
from paula_agent.ui.window import ChatWindow, StageWindow

log = logging.getLogger("paula_agent")


class LazyWakeWord:
    """Starts the detector once the model is available; until then the hotkey still works."""

    def __init__(self) -> None:
        self._detector: WakeWordDetector | None = None
        self._paused = False

    def attach(self, detector: WakeWordDetector) -> None:
        self._detector = detector
        if self._paused:
            detector.pause()
        detector.start()

    def pause(self) -> None:
        self._paused = True
        if self._detector:
            self._detector.pause()

    def resume(self) -> None:
        self._paused = False
        if self._detector:
            self._detector.resume()

    def stop(self) -> None:
        if self._detector:
            self._detector.stop()


def main() -> int:
    # Kept before load_dotenv fills os.environ, so a restart reads settings exactly
    # like a normal start: real environment first, then the (just saved) .env.
    boot_environment = dict(os.environ)
    try:
        settings = Settings.from_env()
    except SettingsError as exc:
        # pythonw has no console: leave the error where it can be found.
        log_dir().mkdir(parents=True, exist_ok=True)
        (log_dir() / "agent-config-error.txt").write_text(str(exc), encoding="utf-8")
        if sys.stderr is not None:
            print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    setup_logging(settings.log_level, "agent")

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    stage, chat = StageWindow(), ChatWindow()

    mic = resolve(settings.mic_device, "input")
    transcriber = Transcriber(
        settings.whisper_model, settings.whisper_language, settings.whisper_device
    )
    speaker = Speaker(
        settings.elevenlabs_api_key,
        settings.elevenlabs_voice_id,
        settings.elevenlabs_model,
        speed=settings.elevenlabs_speed,
        player=SoundDevicePlayer(device=resolve(settings.speaker_device, "output")),
    )
    if not speaker.enabled:
        log.warning("ELEVENLABS_API_KEY is empty: replies will only appear in the chat")
    wake = LazyWakeWord()
    controller: AgentController | None = None

    bus = AgentBus(
        settings.rabbitmq_url,
        settings.agent_shared_secret,
        on_result=lambda result: controller.result_received(result),
        on_action=lambda action: controller.action_received(action),
        seen_actions_path=settings.models_dir.parent / "seen_actions.txt",
    )
    restart = False
    settings_window: SettingsWindow | None = None

    def open_settings() -> None:
        nonlocal settings_window
        # Built fresh each time: devices plugged in since, current memory, and no
        # leftover edits from a cancelled visit.
        if settings_window is not None and settings_window.copying:
            settings_window.show()
            settings_window.raise_()
            return
        if settings_window is not None:
            settings_window.close()
            settings_window.deleteLater()
        settings_window = SettingsWindow(
            settings,
            list_devices=list_devices,
            memory=MemoryFile(log_dir().parent / "memory.sqlite3"),
        )
        settings_window.saved.connect(restart_paula)
        settings_window.show()
        settings_window.raise_()
        settings_window.activateWindow()

    def restart_paula() -> None:
        nonlocal restart
        restart = True
        app.quit()

    controller = AgentController(
        stage,
        chat,
        bus=bus,
        recorder=Recorder(device=mic),
        transcriber=transcriber,
        speaker=speaker,
        runner=CommandRunner(load_apps(settings.apps_file)),
        wake_detector=wake,
        exclusion=ExclusionPolicy.from_names(settings.excluded_apps),
        foreground=foreground_window,
        quit_app=app.quit,
        open_settings=open_settings,
        listen_seconds=settings.hotkey_listen_seconds,
        conversation_seconds=settings.conversation_seconds,
    )
    hotkey = HotkeyListener(controller.hotkey_pressed, controller.escape_pressed, settings.hotkey)

    def warm_up() -> None:
        # Model downloads and loading happen off the UI thread.
        try:
            transcriber.load()
        except Exception:
            log.exception("Could not load the Whisper model")
        try:
            model = ensure_model(settings.models_dir)
            wake.attach(
                WakeWordDetector(
                    model,
                    controller.wake_word_heard,
                    wake_words=settings.wake_words,
                    min_confidence=settings.wake_word_min_confidence,
                    device=mic,
                )
            )
            log.info("Wake word ready")
        except Exception:
            log.exception("Wake word unavailable; use the hotkey")

    stage.place_in_corner()
    stage.show()
    bus.start()
    hotkey.start()
    threading.Thread(target=warm_up, name="warm-up", daemon=True).start()

    code = app.exec()
    hotkey.stop()
    wake.stop()
    bus.stop()
    if restart:
        # New settings are read at start-up. sys.executable is the venv interpreter.
        log.info("Restarting to apply new settings")
        subprocess.Popen(
            [sys.executable, "-m", "paula_agent"],
            cwd=settings.env_file.parent,
            env=boot_environment,
        )
    return code


if __name__ == "__main__":
    sys.exit(main())
