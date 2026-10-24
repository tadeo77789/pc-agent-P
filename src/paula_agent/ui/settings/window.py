"""The Configuración window: audio devices, voice, activation and memory.

Changes are written to `.env` and applied by restarting Paula, so every setting takes
effect the same way. User-facing text is Spanish.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from paula_agent.audio.devices import AudioDevice
from paula_agent.config.env_file import update_env
from paula_agent.config.knowledge_folder import SUFFIXES, KnowledgeFolder
from paula_agent.config.memory_file import MemoryBusy, MemoryFile
from paula_agent.config.settings import Settings
from paula_agent.ui import theme

log = logging.getLogger(__name__)

DEFAULT_DEVICE = "Predeterminado de Windows"
METER_RATE = 16000
TEST_TONE_SECONDS = 0.6


def spawn_thread(work: Callable[[], None]) -> None:
    threading.Thread(target=work, daemon=True).start()


class LevelMeter:
    """Opens the chosen microphone and keeps its latest loudness (0..1)."""

    def __init__(self, device: int | None) -> None:
        import sounddevice as sd

        self.level = 0.0
        self._stream = sd.InputStream(
            samplerate=METER_RATE, channels=1, device=device, callback=self._callback
        )
        self._stream.start()

    def _callback(self, indata, frames, time_info, status) -> None:
        rms = float(np.sqrt(np.mean(np.square(indata[:, 0]))))
        self.level = min(1.0, rms * 8)  # speech sits around 0.02-0.1 RMS

    def close(self) -> None:
        self._stream.stop()
        self._stream.close()


def play_test_tone(device: int | None) -> None:
    import sounddevice as sd

    t = np.linspace(0, TEST_TONE_SECONDS, int(22050 * TEST_TONE_SECONDS), endpoint=False)
    tone = (0.2 * np.sin(2 * np.pi * 660 * t) * np.hanning(t.size)).astype(np.float32)
    sd.play(tone, 22050, device=device)


class SettingsWindow(QWidget):
    saved = Signal()
    _copied = Signal(object)  # (added, skipped) or the error

    def __init__(
        self,
        settings: Settings,
        *,
        list_devices: Callable[[str], list[AudioDevice]],
        memory: MemoryFile,
        knowledge: KnowledgeFolder | None = None,
        pick_files: Callable[[], list[Path]] | None = None,
        confirm: Callable[[str], bool] | None = None,
        run_in_background: Callable[[Callable[[], None]], None] = spawn_thread,
        open_meter: Callable[[int | None], LevelMeter] = LevelMeter,
        play_tone: Callable[[int | None], None] = play_test_tone,
    ) -> None:
        super().__init__(None, Qt.WindowType.Window)
        self.setWindowTitle("Configuración de Paula")
        self.setMinimumWidth(460)
        self.setStyleSheet(f"font-family: '{theme.FONT_FAMILY}'; font-size: 13px;")
        self._settings = settings
        self._env_file: Path = settings.env_file
        self._memory = memory
        self._knowledge = knowledge or (
            KnowledgeFolder(settings.knowledge_dir) if settings.knowledge_dir else None
        )
        # Injected callables only; the defaults are looked up at use time, because storing
        # a bound method of self here would make a reference cycle that the garbage
        # collector may break on another thread (Qt objects must die on the GUI thread).
        self._pick_files = pick_files
        self._confirm = confirm
        self._run = run_in_background
        self._open_meter = open_meter
        self._play_tone = play_tone
        self._meter: LevelMeter | None = None

        tabs = QTabWidget(self)
        tabs.addTab(self._audio_tab(list_devices), "Audio")
        tabs.addTab(self._voice_tab(), "Voz y conversación")
        tabs.addTab(self._activation_tab(), "Activación")
        tabs.addTab(self._memory_tab(), "Memoria")
        if self._knowledge is not None:
            tabs.addTab(self._knowledge_tab(), "Conocimiento")

        self.error = QLabel("")
        self.error.setStyleSheet("color: #B91C1C;")
        self.error.setWordWrap(True)
        self.save_button = QPushButton("Guardar y reiniciar Paula")
        self.save_button.clicked.connect(self.save)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.close)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(self.save_button)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(self.error)
        layout.addLayout(buttons)

        self._meter_timer = QTimer(self, interval=60, timeout=self._update_meter)

    # Tabs

    def _audio_tab(self, list_devices) -> QWidget:
        self.mic = self._device_combo(list_devices("input"), self._settings.mic_device)
        self.speaker = self._device_combo(list_devices("output"), self._settings.speaker_device)
        self.level = QProgressBar(maximum=100, textVisible=False)
        self.level.setFixedHeight(10)
        self.mic.currentIndexChanged.connect(self._restart_meter)
        test = QPushButton("Probar sonido")
        test.clicked.connect(self._test_sound)

        page = QWidget()
        form = QFormLayout(page)
        form.addRow("Micrófono", self.mic)
        form.addRow("Nivel", self.level)
        form.addRow("", QLabel("Habla: si la barra se mueve, Paula te oye por ese micrófono."))
        form.addRow("Salida de voz", self.speaker)
        form.addRow("", test)
        return page

    def _voice_tab(self) -> QWidget:
        self.speed = QDoubleSpinBox(minimum=0.7, maximum=1.2, singleStep=0.05, decimals=2)
        self.speed.setValue(self._settings.elevenlabs_speed)
        self.conversation = QSpinBox(minimum=0, maximum=30, suffix=" s")
        self.conversation.setValue(round(self._settings.conversation_seconds))

        page = QWidget()
        form = QFormLayout(page)
        form.addRow("Velocidad de la voz", self.speed)
        form.addRow("Seguir escuchando tras responder", self.conversation)
        form.addRow("", QLabel("0 s = sin modo conversación (hay que decir «Paula» cada vez)."))
        return page

    def _activation_tab(self) -> QWidget:
        self.confidence = QDoubleSpinBox(minimum=0.5, maximum=0.99, singleStep=0.01, decimals=2)
        self.confidence.setValue(self._settings.wake_word_min_confidence)
        self.listen_seconds = QSpinBox(minimum=3, maximum=15, suffix=" s")
        self.listen_seconds.setValue(self._settings.hotkey_listen_seconds)
        self.excluded = QLineEdit(self._settings.excluded_apps)
        self.excluded.setPlaceholderText("discord.exe, pioneergame.exe")

        page = QWidget()
        form = QFormLayout(page)
        form.addRow("Exigencia al oír «Paula»", self.confidence)
        form.addRow(
            "", QLabel("Más alto = se activa menos por error, pero hay que hablar más claro.")
        )
        form.addRow("Tiempo para hablar con Ctrl+Shift+P", self.listen_seconds)
        form.addRow("Apps donde no escucha su nombre", self.excluded)
        return page

    def _memory_tab(self) -> QWidget:
        self.facts = QListWidget()
        self.facts.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.facts.setWordWrap(True)
        delete = QPushButton("Borrar seleccionados")
        delete.clicked.connect(self._delete_selected)
        self._reload_facts()

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("Lo que Paula recuerda de ti:"))
        layout.addWidget(self.facts)
        layout.addWidget(delete, alignment=Qt.AlignmentFlag.AlignRight)
        return page

    def _knowledge_tab(self) -> QWidget:
        self.documents = QListWidget()
        self.documents.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.add_button = add = QPushButton("Agregar archivos…")
        add.clicked.connect(self._add_documents)
        self._copied.connect(self._on_copied)
        remove = QPushButton("Quitar seleccionados")
        remove.clicked.connect(self._remove_documents)
        folder = QPushButton("Abrir carpeta")
        folder.clicked.connect(self._open_folder)
        self._reload_documents()

        buttons = QHBoxLayout()
        buttons.addWidget(add)
        buttons.addWidget(folder)
        buttons.addStretch()
        buttons.addWidget(remove)
        page = QWidget()
        layout = QVBoxLayout(page)
        hint = QLabel(
            "Documentos de los que Paula aprende (.md, .txt, .pdf). Los nuevos los "
            "aprende en menos de un minuto. También puedes decirle «apréndete esto: …»."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addWidget(self.documents)
        layout.addLayout(buttons)
        return page

    # Behaviour

    def _device_combo(self, devices: list[AudioDevice], current: str) -> QComboBox:
        combo = QComboBox()
        default = next((d.name for d in devices if d.is_default), "")
        combo.addItem(f"{DEFAULT_DEVICE} ({default})" if default else DEFAULT_DEVICE, None)
        for device in devices:
            combo.addItem(device.name, device.index)
        if current:
            found = combo.findText(current)
            if found < 0:  # saved device is unplugged: keep it so saving does not lose it
                combo.addItem(f"{current} (no conectado)", None)
                found = combo.count() - 1
            combo.setCurrentIndex(found)
        return combo

    def _device_name(self, combo: QComboBox) -> str:
        if combo.currentIndex() == 0:
            return ""
        return combo.currentText().removesuffix(" (no conectado)")

    def _test_sound(self) -> None:
        try:
            self._play_tone(self.speaker.currentData())
            self.error.clear()
        except Exception:
            log.exception("Test tone failed")
            self.error.setText("No pude reproducir sonido por esa salida. ¿Está conectada?")

    def _reload_facts(self) -> None:
        self.facts.clear()
        try:
            facts = self._memory.facts()
        except MemoryBusy:
            self._hint("La memoria está ocupada ahora mismo. Vuelve a abrir la ventana.")
            return
        for fact in facts:
            item = QListWidgetItem(fact.text)
            item.setData(Qt.ItemDataRole.UserRole, fact.id)
            self.facts.addItem(item)
        if not facts:
            self._hint("Paula todavía no recuerda nada.")

    def _hint(self, text: str) -> None:
        item = QListWidgetItem(text)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        self.facts.addItem(item)

    def _delete_selected(self) -> None:
        ids = [item.data(Qt.ItemDataRole.UserRole) for item in self.facts.selectedItems()]
        try:
            self._memory.delete([i for i in ids if i])
            self.error.clear()
        except MemoryBusy:
            self.error.setText("La memoria está ocupada. Inténtalo de nuevo en un momento.")
        self._reload_facts()

    def _reload_documents(self) -> None:
        self.documents.clear()
        names = self._knowledge.files()
        self.documents.addItems(names)
        if not names:
            item = QListWidgetItem("Todavía no hay documentos.")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.documents.addItem(item)

    def _add_documents(self) -> None:
        sources = (self._pick_files or self._ask_for_files)()
        if not sources:
            return
        self.add_button.setEnabled(False)
        self.error.setText("Copiando…")

        def work() -> None:
            # Off the UI thread: a big PDF or a network share must not freeze Paula.
            try:
                result = self._knowledge.add(sources)
            except OSError as exc:
                log.exception("Could not copy documents")
                result = exc
            self._copied.emit(result)

        self._run(work)

    def _on_copied(self, result) -> None:
        self.add_button.setEnabled(True)
        if isinstance(result, Exception):
            self.error.setText("No pude copiar todos los archivos a la carpeta de conocimiento.")
        else:
            _, skipped = result
            self.error.setText("No se agregaron: " + ", ".join(skipped) if skipped else "")
        self._reload_documents()  # also after a failure: some files may have been copied

    def _remove_documents(self) -> None:
        names = [
            i.text()
            for i in self.documents.selectedItems()
            if i.flags() & Qt.ItemFlag.ItemIsEnabled
        ]
        if not names:
            return
        question = (
            f"¿Quitar {len(names)} documento(s)? Paula dejará de usarlos y se borrarán "
            "de la carpeta de conocimiento."
        )
        if not (self._confirm or self._ask_to_confirm)(question):
            return
        try:
            self._knowledge.remove(names)
            self.error.clear()
        except (OSError, ValueError):
            log.exception("Could not remove documents")
            self.error.setText("No pude quitar alguno de los documentos.")
        self._reload_documents()

    def _open_folder(self) -> None:
        try:
            self._knowledge.open_in_explorer()
        except OSError:
            self.error.setText("No pude abrir la carpeta de conocimiento.")

    def _ask_for_files(self) -> list[Path]:
        patterns = " ".join(f"*{s}" for s in SUFFIXES)
        names, _ = QFileDialog.getOpenFileNames(
            self, "Agregar documentos", str(Path.home()), f"Documentos ({patterns})"
        )
        return [Path(n) for n in names]

    def _ask_to_confirm(self, question: str) -> bool:
        answer = QMessageBox.question(self, "Paula", question)
        return answer == QMessageBox.StandardButton.Yes

    def changes(self) -> dict[str, str]:
        return {
            "MIC_DEVICE": self._device_name(self.mic),
            "SPEAKER_DEVICE": self._device_name(self.speaker),
            "ELEVENLABS_SPEED": f"{self.speed.value():.2f}",
            "CONVERSATION_SECONDS": str(self.conversation.value()),
            "WAKE_WORD_MIN_CONFIDENCE": f"{self.confidence.value():.2f}",
            "HOTKEY_LISTEN_SECONDS": str(self.listen_seconds.value()),
            "EXCLUDED_APPS": ",".join(
                name.strip().lower() for name in self.excluded.text().split(",") if name.strip()
            ),
        }

    def save(self) -> None:
        try:
            update_env(self._env_file, self.changes())
        except ValueError:
            self.error.setText("Algún valor tiene caracteres no permitidos (saltos de línea o ${).")
            return
        except OSError:
            log.exception("Could not write %s", self._env_file)
            self.error.setText("No pude guardar la configuración. ¿El archivo .env está abierto?")
            return
        self.close()
        self.saved.emit()

    # Live microphone level, only while the window is open

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._restart_meter()

    def closeEvent(self, event) -> None:
        self._stop_meter()
        super().closeEvent(event)

    def _restart_meter(self) -> None:
        self._stop_meter()
        if not self.isVisible():
            return
        try:
            self._meter = self._open_meter(self.mic.currentData())
            self._meter_timer.start()
        except Exception:
            log.exception("Could not open the microphone for the level meter")

    def _stop_meter(self) -> None:
        self._meter_timer.stop()
        if self._meter is not None:
            self._meter.close()
            self._meter = None
        self.level.setValue(0)

    def _update_meter(self) -> None:
        if self._meter is not None:
            self.level.setValue(int(self._meter.level * 100))
