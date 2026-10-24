"""Run the agent: python -m paula_agent"""

from __future__ import annotations

import logging
import sys
import threading

from PySide6.QtWidgets import QApplication

from paula_agent.activation.foreground import ExclusionPolicy, foreground_window
from paula_agent.activation.hotkey import HotkeyListener
from paula_agent.activation.wake_word import WakeWordDetector, ensure_model
from paula_agent.audio.recorder import Recorder
from paula_agent.audio.stt import Transcriber
from paula_agent.audio.tts import Speaker
from paula_agent.commands.runner import CommandRunner, load_apps
from paula_agent.config.settings import Settings, SettingsError
from paula_agent.controller import AgentController, settings_opener
from paula_agent.messaging.bus import AgentBus
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
    try:
        settings = Settings.from_env()
    except SettingsError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    stage, chat = StageWindow(), ChatWindow()

    transcriber = Transcriber(settings.whisper_model, settings.whisper_language)
    speaker = Speaker(
        settings.elevenlabs_api_key, settings.elevenlabs_voice_id, settings.elevenlabs_model
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
    )
    controller = AgentController(
        stage,
        chat,
        bus=bus,
        recorder=Recorder(),
        transcriber=transcriber,
        speaker=speaker,
        runner=CommandRunner(load_apps(settings.apps_file)),
        wake_detector=wake,
        exclusion=ExclusionPolicy.from_names(settings.excluded_apps),
        foreground=foreground_window,
        open_settings=settings_opener(settings.env_file),
        listen_seconds=settings.hotkey_listen_seconds,
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
    return code


if __name__ == "__main__":
    sys.exit(main())
