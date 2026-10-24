"""The four clouds that pop around Paula when she is clicked."""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QPushButton, QWidget

from paula_agent.ui import theme

# (id, label, corner); labels are user-facing, in Spanish
CLOUDS = (
    ("settings", "⚙️ Configuración", "top"),
    ("chat", "💬 Abrir chat", "top-left"),
    ("commands", "⚡ Ver comandos", "top-right"),
    ("quit", "🔌 Apagar Paula", "bottom-left"),
    ("sleep", "🌙 Dormir", "bottom-right"),
)
STAGGER_MS = 80
# Clouds hug the robot: each one overlaps the robot's column by OVERLAP pixels and
# leaves GAP pixels above or below it, so the two dots still fit in between.
OVERLAP = 22
GAP = 12  # at least BODY_MARGIN's bottom, so no cloud sits under the robot widget
# The robot is painted inside its widget with this margin (left, top, right, bottom)
# so it can grow on hover; clouds hug the painted body, not the widget.
BODY_MARGIN = (15, 6, 13, 12)


class CloudButton(QPushButton):
    hovered = Signal(object)  # global center QPoint, or None on leave

    def __init__(self, cloud_id: str, label: str, parent: QWidget) -> None:
        super().__init__(label, parent)
        self.cloud_id = cloud_id
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            f"""
            QPushButton {{
                background: {theme.CLOUD_BG}; color: {theme.CLOUD_TEXT};
                border: none; border-radius: 18px; padding: 10px 16px;
                font-family: '{theme.FONT_FAMILY}'; font-size: 13px;
            }}
            QPushButton:hover {{ background: {theme.CLOUD_HOVER}; color: white; }}
            """
        )
        shadow = QGraphicsDropShadowEffect(self, blurRadius=16, offset=QPoint(0, 6))
        shadow.setColor(QColor(0, 0, 0, 56))
        self.setGraphicsEffect(shadow)
        self.adjustSize()

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self.hovered.emit(self.mapToGlobal(self.rect().center()))

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self.hovered.emit(None)


class Dot(QWidget):
    def __init__(self, size: int, parent: QWidget) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setStyleSheet(f"background: white; border-radius: {size // 2}px;")


class CloudMenu(QWidget):
    """Overlay the size of the stage. Emits `picked(cloud_id)`."""

    picked = Signal(str)
    hovered = Signal(object)

    def __init__(self, parent: QWidget, robot_rect: QRect) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(parent.rect())
        left, top, right, bottom = BODY_MARGIN
        self._robot_rect = robot_rect.adjusted(left, top, -right, -bottom)
        self._open = False
        self._buttons: list[CloudButton] = []
        self._dots: list[Dot] = []
        self._animations: list[QPropertyAnimation] = []
        for cloud_id, label, corner in CLOUDS:
            button = CloudButton(cloud_id, label, self)
            button.move(self._corner_position(button, corner))
            button.clicked.connect(lambda _=False, c=cloud_id: self._pick(c))
            button.hovered.connect(self.hovered.emit)
            button.hide()
            self._buttons.append(button)
        self._build_dots()
        self.hide()

    @property
    def is_open(self) -> bool:
        return self._open

    def toggle(self) -> None:
        self.close_menu() if self.is_open else self.open_menu()

    def open_menu(self) -> None:
        # Not raised above the robot: a second click on Paula has to reach her to close it.
        self._open = True
        self.show()
        for dot in self._dots:
            dot.show()
        for i, button in enumerate(self._buttons):
            QTimer.singleShot(i * STAGGER_MS, lambda b=button: self._pop(b))

    def close_menu(self) -> None:
        self._open = False
        for animation in self._animations:
            animation.stop()
        self._animations.clear()
        for widget in (*self._buttons, *self._dots):
            widget.hide()
        self.hide()
        self.hovered.emit(None)

    def _pick(self, cloud_id: str) -> None:
        self.close_menu()
        self.picked.emit(cloud_id)

    def _pop(self, button: CloudButton) -> None:
        if not self.is_open:
            return
        end = button.geometry()
        start = QRect(end.center(), end.size() * 0.4)
        start.moveCenter(end.center())
        animation = QPropertyAnimation(button, b"geometry", self, duration=350)
        animation.setStartValue(start)
        animation.setEndValue(end)
        animation.setEasingCurve(QEasingCurve.Type.OutBack)
        button.show()
        animation.start()
        self._animations.append(animation)

    def _corner_position(self, button: CloudButton, corner: str) -> QPoint:
        robot = self._robot_rect
        if corner == "top":
            # Centered above the two top clouds.
            x = robot.center().x() - button.width() // 2
            return QPoint(x, robot.top() - 2 * (GAP + button.height()))
        if corner.endswith("left"):
            x = robot.left() + OVERLAP - button.width()
        else:
            x = robot.right() - OVERLAP
        if corner.startswith("top"):
            y = robot.top() - GAP - button.height()
        else:
            y = robot.bottom() + 1 + GAP  # QRect.bottom() is the last row, inclusive
        return QPoint(x, y)

    def _build_dots(self) -> None:
        center = self._robot_rect.center()
        for button in self._buttons:
            cloud = button.geometry().center()
            start, end = cloud, center
            for t, size in ((0.3, 8), (0.42, 5)):
                x = start.x() + (end.x() - start.x()) * t
                y = start.y() + (end.y() - start.y()) * t
                dot = Dot(size, self)
                dot.move(int(x - size / 2), int(y - size / 2))
                dot.hide()
                self._dots.append(dot)
