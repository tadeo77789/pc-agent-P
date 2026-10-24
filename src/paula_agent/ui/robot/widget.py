"""The robot, drawn in the 120x100 coordinate space of assets/robot/*.svg."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QCursor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from paula_agent.ui import theme
from paula_agent.ui.robot.states import BODY, EARS, SCREEN, STATE_STYLES, RobotState

VIEW_W, VIEW_H = 120.0, 100.0
BLINK_EVERY_MS = 4000
BLINK_MS = 120
TALK_MS = 300


DRAG_THRESHOLD = 6  # pixels the mouse must move before a press becomes a drag


def _quad(start, control, end) -> QPainterPath:
    path = QPainterPath(QPointF(*start))
    path.quadTo(QPointF(*control), QPointF(*end))
    return path


class RobotWidget(QWidget):
    clicked = Signal()
    # Dragging Paula moves her window; a short press is still a click.
    drag_started = Signal()
    dragged = Signal(QPoint)  # offset from where the press started
    drag_finished = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(*theme.ROBOT_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._press: QPoint | None = None
        self._dragging = False
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._state = RobotState.SLEEPING
        self._hover = False
        self._blinking = False
        self._talk = 1.0
        self._shake = 0.0
        self._eye_offset = QPointF(0, 0)
        self._look_target: QPoint | None = None

        self._blink_timer = QTimer(self, interval=BLINK_EVERY_MS, timeout=self._blink)
        self._blink_timer.start()
        self._track_timer = QTimer(self, interval=50, timeout=self._track)
        self._track_timer.start()

        self._talk_anim = QVariantAnimation(
            self, startValue=1.0, endValue=0.4, duration=TALK_MS, loopCount=-1
        )
        self._talk_anim.valueChanged.connect(self._set_talk)
        self._shake_anim = QVariantAnimation(self, duration=400)
        self._shake_anim.setKeyValues([(0.0, 0.0), (0.25, -5.0), (0.75, 5.0), (1.0, 0.0)])
        self._shake_anim.valueChanged.connect(self._set_shake)

    # Public API

    @property
    def state(self) -> RobotState:
        return self._state

    def set_state(self, state: RobotState | str) -> None:
        self._state = RobotState(state)
        if self._state is RobotState.SPEAKING:
            self._talk_anim.start()
        else:
            self._talk_anim.stop()
            self._talk = 1.0
        if self._state is RobotState.ANGRY:
            self._shake_anim.stop()
            self._shake_anim.start()
        self.update()

    def look_at(self, point: QPoint | None) -> None:
        """Look at a global screen point (a hovered cloud) instead of the cursor."""
        self._look_target = point

    # Animation callbacks

    def _blink(self) -> None:
        self._blinking = True
        self.update()
        QTimer.singleShot(BLINK_MS, self._end_blink)

    def _end_blink(self) -> None:
        self._blinking = False
        self.update()

    def _set_talk(self, value) -> None:
        self._talk = float(value)
        self.update()

    def _set_shake(self, value) -> None:
        self._shake = float(value)
        self.update()

    def _track(self) -> None:
        target = self._look_target or QCursor.pos()
        center = self.mapToGlobal(self.rect().center())
        dx = max(-5.0, min(5.0, (target.x() - center.x()) / 25))
        dy = max(-3.0, min(3.0, (target.y() - center.y()) / 25))
        if (dx, dy) != (self._eye_offset.x(), self._eye_offset.y()):
            self._eye_offset = QPointF(dx, dy)
            self.update()

    # Qt events

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.globalPosition().toPoint()
            self._dragging = False

    def mouseMoveEvent(self, event) -> None:
        if self._press is None:
            return
        delta = event.globalPosition().toPoint() - self._press
        if not self._dragging and delta.manhattanLength() < DRAG_THRESHOLD:
            return
        if not self._dragging:
            self._dragging = True
            self.drag_started.emit()
        self.dragged.emit(delta)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._dragging:
            self.drag_finished.emit()
        else:
            self.clicked.emit()
        self._press = None
        self._dragging = False

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale = 1.06 if self._hover else 1.0
        painter.translate(self.width() / 2 + self._shake, self.height() / 2)
        painter.scale(scale * self.width() / VIEW_W, scale * self.height() / VIEW_H)
        painter.translate(-VIEW_W / 2, -VIEW_H / 2)

        style = STATE_STYLES[self._state]
        painter.setPen(Qt.PenStyle.NoPen)
        for rect, radius, color in (
            ((22, 6, 76, 10), 3, BODY),
            ((14, 14, 92, 74), 8, BODY),
            ((8, 34, 8, 18), 2, EARS),
            ((104, 34, 8, 18), 2, EARS),
            ((18, 20, 84, 62), 6, style.frame),
            ((26, 27, 68, 48), 4, SCREEN),
        ):
            painter.setBrush(QColor(color))
            painter.drawRoundedRect(QRectF(*rect), radius, radius)

        accent = QColor(style.accent)
        painter.save()
        painter.translate(self._eye_offset)
        self._draw_eyes(painter, accent)
        painter.restore()
        self._draw_mouth(painter, accent)
        painter.end()

    # Faces (shapes copied from paula_estilos.html)

    def _stroke(self, painter: QPainter, color: QColor, width: float) -> None:
        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    def _fill(self, painter: QPainter, color: QColor) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)

    def _blink_rect(self, painter: QPainter, x, y, w, h) -> None:
        if self._blinking:
            y, h = y + h * 0.45, h * 0.1
        painter.drawRect(QRectF(x, y, w, h))

    def _draw_eyes(self, painter: QPainter, color: QColor) -> None:
        s = self._state
        if s is RobotState.SLEEPING:
            self._stroke(painter, color, 3)
            painter.drawPath(_quad((38, 52), (46, 58), (54, 52)))
            painter.drawPath(_quad((66, 52), (74, 58), (82, 52)))
        elif s is RobotState.LISTENING:
            self._fill(painter, color)
            self._blink_rect(painter, 40, 42, 10, 14)
            self._blink_rect(painter, 70, 42, 10, 14)
        elif s is RobotState.THINKING:
            self._fill(painter, color)
            self._blink_rect(painter, 36, 40, 10, 12)
            self._blink_rect(painter, 66, 40, 10, 12)
        elif s is RobotState.SPEAKING:
            self._stroke(painter, color, 3)
            painter.drawPath(_quad((38, 50), (45, 40), (52, 50)))
            painter.drawPath(_quad((68, 50), (75, 40), (82, 50)))
        elif s is RobotState.QUESTION:
            self._fill(painter, color)
            self._blink_rect(painter, 40, 42, 10, 12)
            self._blink_rect(painter, 70, 40, 10, 14)
            self._stroke(painter, color, 3)
            painter.drawLine(QPointF(68, 36), QPointF(82, 34))
        elif s is RobotState.ANGRY:
            self._stroke(painter, color, 4)
            painter.drawLine(QPointF(34, 40), QPointF(54, 48))
            painter.drawLine(QPointF(86, 40), QPointF(66, 48))
            self._fill(painter, color)
            painter.drawRect(QRectF(40, 48, 10, 8))
            painter.drawRect(QRectF(70, 48, 10, 8))

    def _draw_mouth(self, painter: QPainter, color: QColor) -> None:
        s = self._state
        if s is RobotState.SLEEPING:
            self._fill(painter, color)
            painter.drawRect(QRectF(50, 64, 20, 3))
        elif s is RobotState.LISTENING:
            self._fill(painter, color)
            painter.drawRoundedRect(QRectF(56, 62, 8, 6), 2, 2)
        elif s is RobotState.THINKING:
            self._stroke(painter, color, 3)
            path = _quad((46, 66), (52, 62), (58, 66))
            path.quadTo(QPointF(64, 70), QPointF(70, 66))
            painter.drawPath(path)
        elif s is RobotState.SPEAKING:
            self._fill(painter, color)
            painter.save()
            painter.translate(60, 66)
            painter.scale(1.0, self._talk)
            painter.translate(-60, -66)
            path = _quad((44, 62), (60, 76), (76, 62))
            path.closeSubpath()
            painter.drawPath(path)
            painter.restore()
        elif s is RobotState.QUESTION:
            self._fill(painter, color)
            painter.drawEllipse(QPointF(60, 66), 4, 3)
        elif s is RobotState.ANGRY:
            self._stroke(painter, color, 3)
            painter.drawPath(_quad((46, 72), (60, 62), (74, 72)))
