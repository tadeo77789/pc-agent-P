"""Top-level windows: the transparent stage in the screen corner, and the chat."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from paula_agent.ui import theme
from paula_agent.ui.chat.panel import ChatPanel
from paula_agent.ui.clouds.menu import CloudMenu
from paula_agent.ui.robot.states import RobotState
from paula_agent.ui.robot.widget import RobotWidget

SCREEN_MARGIN = 16
FLOATING = (
    Qt.WindowType.FramelessWindowHint
    | Qt.WindowType.WindowStaysOnTopHint
    | Qt.WindowType.Tool  # no taskbar button
)


class StageWindow(QWidget):
    """Only the robot is visible at rest; transparent pixels let clicks through."""

    cloud_picked = Signal(str)

    def __init__(self) -> None:
        super().__init__(None, FLOATING)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(*theme.STAGE_SIZE)

        self.robot = RobotWidget(self)
        robot_w, robot_h = theme.ROBOT_SIZE
        self.robot.move((self.width() - robot_w) // 2, (self.height() - robot_h) // 2)

        self.clouds = CloudMenu(self, QRect(self.robot.pos(), self.robot.size()))
        self.clouds.picked.connect(self.cloud_picked.emit)
        self.clouds.hovered.connect(self.robot.look_at)
        self.robot.clicked.connect(self.clouds.toggle)
        self.robot.raise_()

        self._listen = QLabel(self)
        self._listen.setStyleSheet(
            f"background: white; color: {theme.CLOUD_TEXT}; border-radius: 12px;"
            f" padding: 10px 16px; font-family: '{theme.FONT_FAMILY}'; font-size: 13px;"
        )
        self._listen.hide()

    def place_in_corner(self) -> None:
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(
            screen.right() - self.width() - SCREEN_MARGIN,
            screen.bottom() - self.height() - SCREEN_MARGIN,
        )

    def set_state(self, state: RobotState | str) -> None:
        self.robot.set_state(state)

    def show_listen(self, seconds: int) -> None:
        # User-facing banner, Spanish
        self._listen.setText(
            f"Escuchando… <b style='color:{theme.CLOUD_HOVER}'>{seconds}</b>s · ESC para cancelar"
        )
        self._listen.adjustSize()
        self._listen.move((self.width() - self._listen.width()) // 2, 0)
        self._listen.show()
        self._listen.raise_()

    def hide_listen(self) -> None:
        self._listen.hide()

    @property
    def listen_visible(self) -> bool:
        return self._listen.isVisible()


class ChatWindow(QWidget):
    def __init__(self) -> None:
        super().__init__(None, FLOATING)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.panel = ChatPanel(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.panel)
        self.panel.closed.connect(self.hide)

    def open_next_to(self, stage: QWidget) -> None:
        """Open to the left of the stage, bottom-aligned with the robot."""
        anchor = stage.mapToGlobal(QPoint(0, stage.height() // 2 + theme.ROBOT_SIZE[1] // 2))
        self.move(anchor.x() - self.width() + 60, anchor.y() - self.height())
        self.show()
        self.raise_()
        self.activateWindow()
        self.panel.focus_input()
