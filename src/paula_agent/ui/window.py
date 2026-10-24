"""Top-level windows: the transparent stage in the screen corner, and the chat."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSettings, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from paula_agent.ui import theme
from paula_agent.ui.chat.panel import ChatPanel
from paula_agent.ui.clouds.menu import BODY_MARGIN, CloudMenu
from paula_agent.ui.robot.states import RobotState
from paula_agent.ui.robot.widget import RobotWidget

SCREEN_MARGIN = 16
CHAT_GAP = 12
POSITION_KEY = "stage/position"
FLOATING = (
    Qt.WindowType.FramelessWindowHint
    | Qt.WindowType.WindowStaysOnTopHint
    | Qt.WindowType.Tool  # no taskbar button
)


class StageWindow(QWidget):
    """Only the robot is visible at rest; transparent pixels let clicks through."""

    cloud_picked = Signal(str)

    def __init__(self, settings: QSettings | None = None) -> None:
        super().__init__(None, FLOATING)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(*theme.STAGE_SIZE)
        self._settings = settings or QSettings("PaulaPort", "agent")
        self._drag_origin = QPoint()

        self.robot = RobotWidget(self)
        robot_w, robot_h = theme.ROBOT_SIZE
        self.robot.move((self.width() - robot_w) // 2, (self.height() - robot_h) // 2)

        self.clouds = CloudMenu(self, QRect(self.robot.pos(), self.robot.size()))
        self.clouds.picked.connect(self.cloud_picked.emit)
        self.clouds.hovered.connect(self.robot.look_at)
        self.robot.clicked.connect(self.clouds.toggle)
        self.robot.drag_started.connect(self._start_drag)
        self.robot.dragged.connect(self._drag)
        self.robot.drag_finished.connect(self._save_position)
        self.robot.raise_()

        self._listen = QLabel(self)
        self._listen.setStyleSheet(
            f"background: white; color: {theme.CLOUD_TEXT}; border-radius: 12px;"
            f" padding: 10px 16px; font-family: '{theme.FONT_FAMILY}'; font-size: 13px;"
        )
        self._listen.hide()

    def place_in_corner(self) -> None:
        """Where the user last left Paula, or the bottom-right corner."""
        saved = self._settings.value(POSITION_KEY)
        if isinstance(saved, QPoint) and self._screen_for(saved) is not None:
            self.move(self._clamped(saved))
            return
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(
            screen.right() - self.width() - SCREEN_MARGIN,
            screen.bottom() - self.height() - SCREEN_MARGIN,
        )

    def body_rect(self, pos: QPoint | None = None) -> QRect:
        """The painted robot in global coordinates if the stage were at `pos`."""
        pos = self.pos() if pos is None else pos
        left, top, right, bottom = BODY_MARGIN
        robot = QRect(pos + self.robot.pos(), self.robot.size())
        return robot.adjusted(left, top, -right, -bottom)

    def _screen_for(self, pos: QPoint) -> QRect | None:
        # A monitor may have been unplugged since the position was saved.
        body = self.body_rect(pos)
        areas = [s.availableGeometry() for s in QGuiApplication.screens()]
        touching = [a for a in areas if a.intersects(body)]
        if not touching:
            return None
        return max(
            touching, key=lambda a: a.intersected(body).width() * a.intersected(body).height()
        )

    def _clamped(self, pos: QPoint) -> QPoint:
        """Keep the whole painted robot on one screen, so she can always be grabbed."""
        # A fast drag can jump past the edge: then stick to the screen she is on.
        area = (
            self._screen_for(pos)
            or self._screen_for(self.pos())
            or QGuiApplication.primaryScreen().availableGeometry()
        )
        body = self.body_rect(pos)
        dx = max(area.left() - body.left(), 0) + min(area.right() - body.right(), 0)
        dy = max(area.top() - body.top(), 0) + min(area.bottom() - body.bottom(), 0)
        return pos + QPoint(dx, dy)

    def _start_drag(self) -> None:
        self.clouds.close_menu()
        self._drag_origin = self.pos()

    def _drag(self, offset: QPoint) -> None:
        self.move(self._clamped(self._drag_origin + offset))

    def _save_position(self) -> None:
        self._settings.setValue(POSITION_KEY, self.pos())

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

    def open_next_to(self, stage: StageWindow) -> None:
        """Open to the left of the robot, bottom-aligned with it; to the right if there is
        no room, and always inside the robot's screen."""
        body = stage.body_rect()
        screen = QGuiApplication.screenAt(body.center()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        x = body.left() - CHAT_GAP - self.width()
        if x < area.left():
            x = body.right() + CHAT_GAP
        y = body.bottom() - self.height()
        x = min(max(x, area.left()), area.right() - self.width())
        y = min(max(y, area.top()), area.bottom() - self.height())
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        self.panel.focus_input()
