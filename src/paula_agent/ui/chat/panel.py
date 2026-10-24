"""Chat panel: header, bubbles, option buttons and input."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from paula_agent.ui import theme

GREETING = "Hola, soy Paula. ¿En qué te ayudo?"


class Bubble(QLabel):
    def __init__(self, text: str, role: str) -> None:
        super().__init__(text)
        self.role = role
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        user = role == "user"
        self.setStyleSheet(
            f"""
            background: {theme.BUBBLE_USER if user else theme.BUBBLE_ASSISTANT};
            color: {"white" if user else theme.CLOUD_TEXT};
            border-radius: 10px; padding: 8px 11px; font-size: 13px;
            """
        )
        self.setMaximumWidth(int(theme.CHAT_SIZE[0] * 0.8))


class ChatPanel(QFrame):
    message_sent = Signal(str)
    option_chosen = Signal(str)
    closed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("chat")
        self.setFixedSize(*theme.CHAT_SIZE)
        self.setStyleSheet(
            f"""
            #chat {{ background: white; border-radius: 12px; }}
            #header {{ background: {theme.CHAT_HEADER}; border-top-left-radius: 12px;
                       border-top-right-radius: 12px; }}
            #header QLabel {{ color: white; font-weight: bold; }}
            #header QPushButton {{ background: rgba(255,255,255,0.15); color: white;
                                   border: none; border-radius: 6px; }}
            #messages, #messagesInner, #options {{ background: {theme.CHAT_BG}; }}
            #options QPushButton {{ background: {theme.OPTION}; color: white; border: none;
                                    border-radius: 14px; padding: 6px 12px; font-size: 12px; }}
            #options QPushButton:hover {{ background: {theme.OPTION_HOVER}; }}
            QLineEdit {{ background: white; color: {theme.CLOUD_TEXT};
                         border: 1px solid {theme.INPUT_BORDER}; border-radius: 6px;
                         padding: 7px 9px; font-size: 13px; }}
            #send {{ background: {theme.BUBBLE_USER}; color: white; border: none;
                     border-radius: 6px; }}
            #inputRow {{ background: white; border-top: 1px solid {theme.BORDER};
                         border-bottom-left-radius: 12px; border-bottom-right-radius: 12px; }}
            * {{ font-family: '{theme.FONT_FAMILY}'; }}
            """
        )

        header = QFrame(objectName="header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 10, 14, 10)
        header_layout.addWidget(QLabel("Paula"))
        header_layout.addStretch()
        close = QPushButton("✕")
        close.setFixedSize(24, 24)
        close.clicked.connect(self.closed.emit)
        header_layout.addWidget(close)

        inner = QWidget(objectName="messagesInner")
        self._messages = QVBoxLayout(inner)
        self._messages.setContentsMargins(12, 12, 12, 12)
        self._messages.setSpacing(8)
        self._messages.addStretch()
        self._scroll = QScrollArea(objectName="messages")
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidget(inner)

        self._options_box = QWidget(objectName="options")
        self._options = QHBoxLayout(self._options_box)
        self._options.setContentsMargins(12, 0, 12, 10)
        self._options.setSpacing(6)
        self._options_box.hide()

        input_row = QFrame(objectName="inputRow")
        input_layout = QHBoxLayout(input_row)
        input_layout.setContentsMargins(10, 10, 10, 10)
        self._input = QLineEdit(placeholderText="Escribe un mensaje...")
        self._input.returnPressed.connect(self._send)
        send = QPushButton("➤", objectName="send")
        send.setFixedWidth(34)
        send.clicked.connect(self._send)
        input_layout.addWidget(self._input)
        input_layout.addWidget(send)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header)
        layout.addWidget(self._scroll, 1)
        layout.addWidget(self._options_box)
        layout.addWidget(input_row)

        self.add_message("assistant", GREETING)

    # Public API

    def add_message(self, role: str, text: str) -> None:
        row = QHBoxLayout()
        bubble = Bubble(text, role)
        if role == "user":
            row.addStretch()
        row.addWidget(bubble)
        if role != "user":
            row.addStretch()
        self._messages.insertLayout(self._messages.count() - 1, row)
        QTimer.singleShot(0, self._scroll_to_bottom)

    def show_options(self, options: list[str]) -> None:
        self.clear_options()
        for option in options:
            button = QPushButton(option)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, o=option: self._choose(o))
            self._options.addWidget(button)
        self._options.addStretch()
        self._options_box.show()

    def clear_options(self) -> None:
        while self._options.count():
            item = self._options.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._options_box.hide()

    def bubbles(self) -> list[Bubble]:
        return self.findChildren(Bubble)

    def focus_input(self) -> None:
        self._input.setFocus()

    # Internals

    def _send(self) -> None:
        text = self._input.text().strip()
        if not text:
            return
        self._input.clear()
        self.clear_options()
        self.add_message("user", text)
        self.message_sent.emit(text)

    def _choose(self, option: str) -> None:
        self.clear_options()
        self.add_message("user", option)
        self.option_chosen.emit(option)

    def _scroll_to_bottom(self) -> None:
        bar = self._scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
