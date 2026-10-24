from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton

from paula_agent.ui.chat.panel import GREETING, ChatPanel
from paula_agent.ui.robot.states import STATE_STYLES, RobotState, svg_path
from paula_agent.ui.robot.widget import RobotWidget
from paula_agent.ui.window import ChatWindow, StageWindow


def render(widget) -> QImage:
    image = QImage(widget.size(), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    widget.render(image)
    return image


def test_every_state_has_svg_asset():
    for state in RobotState:
        assert svg_path(state).exists()


def test_robot_paints_frame_color_of_each_state(qapp):
    robot = RobotWidget()
    for state in RobotState:
        robot.set_state(state)
        image = render(robot)
        # Left edge of the colored frame, between body and screen (x=20/120, y=50/100)
        pixel = image.pixelColor(int(robot.width() * 20 / 120), int(robot.height() * 50 / 100))
        assert pixel.name().lower() == STATE_STYLES[state].frame.lower(), state


def test_robot_click_emits_signal(qapp):
    robot = RobotWidget()
    clicks = []
    robot.clicked.connect(lambda: clicks.append(1))

    QTest.mouseClick(robot, Qt.MouseButton.LeftButton)

    assert clicks == [1]


def test_angry_state_shakes(qapp):
    robot = RobotWidget()

    robot.set_state("angry")

    assert robot._shake_anim.state() == robot._shake_anim.State.Running


def test_chat_starts_with_greeting_and_sends(qapp):
    panel = ChatPanel()
    sent = []
    panel.message_sent.connect(sent.append)

    QTest.keyClicks(panel._input, "abre el navegador")
    QTest.keyClick(panel._input, Qt.Key.Key_Return)

    texts = [(b.role, b.text()) for b in panel.bubbles()]
    assert texts == [("assistant", GREETING), ("user", "abre el navegador")]
    assert sent == ["abre el navegador"]


def test_chat_options_emit_choice_and_disappear(qapp):
    panel = ChatPanel()
    chosen = []
    panel.option_chosen.connect(chosen.append)

    panel.show_options(["Sí, confirmo", "No"])
    buttons = panel._options_box.findChildren(QPushButton)
    assert [b.text() for b in buttons] == ["Sí, confirmo", "No"]

    buttons[0].click()

    assert chosen == ["Sí, confirmo"]
    assert panel._options_box.isHidden()


def test_stage_clouds_toggle_and_pick(qapp):
    stage = StageWindow()
    picked = []
    stage.cloud_picked.connect(picked.append)

    stage.robot.clicked.emit()
    assert stage.clouds.is_open

    stage.clouds._buttons[0].click()

    assert picked == ["chat"]
    assert not stage.clouds.is_open


def test_stage_listen_banner(qapp):
    stage = StageWindow()
    stage.show()

    stage.show_listen(5)
    assert stage.listen_visible
    stage.hide_listen()
    assert not stage.listen_visible


def test_chat_window_opens_next_to_stage(qapp):
    stage = StageWindow()
    stage.move(QPoint(800, 400))
    chat = ChatWindow()

    chat.open_next_to(stage)

    assert chat.isVisible()
    assert chat.x() < stage.x() + stage.width() // 2
