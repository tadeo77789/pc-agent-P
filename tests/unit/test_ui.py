from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtGui import QGuiApplication, QImage
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

    next(b for b in stage.clouds._buttons if b.cloud_id == "chat").click()

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


def test_bubbles_render_plain_text(qapp):
    panel = ChatPanel()

    panel.add_message("assistant", "<b>hola</b>")

    assert panel.bubbles()[-1].textFormat() == Qt.TextFormat.PlainText


def temp_settings(tmp_path) -> QSettings:
    return QSettings(str(tmp_path / "agent.ini"), QSettings.Format.IniFormat)


def test_dragging_moves_the_stage_without_clicking(qapp, tmp_path):
    stage = StageWindow(temp_settings(tmp_path))
    stage.move(200, 200)
    clicks = []
    stage.robot.clicked.connect(lambda: clicks.append(1))
    stage.clouds.open_menu()

    stage.robot.drag_started.emit()
    stage.robot.dragged.emit(QPoint(-40, -30))
    stage.robot.drag_finished.emit()

    assert stage.pos() == QPoint(160, 170)
    assert not stage.clouds.is_open
    assert clicks == []


def test_small_press_movement_is_still_a_click(qapp):
    robot = RobotWidget()
    events = []
    robot.clicked.connect(lambda: events.append("click"))
    robot.drag_started.connect(lambda: events.append("drag"))

    QTest.mousePress(robot, Qt.MouseButton.LeftButton, pos=QPoint(50, 50))
    QTest.mouseMove(robot, QPoint(52, 51))
    QTest.mouseRelease(robot, Qt.MouseButton.LeftButton, pos=QPoint(52, 51))

    assert events == ["click"]


def test_position_is_remembered(qapp, tmp_path):
    stage = StageWindow(temp_settings(tmp_path))
    stage.move(300, 250)
    stage._save_position()

    again = StageWindow(temp_settings(tmp_path))
    again.place_in_corner()

    assert again.pos() == QPoint(300, 250)


def test_offscreen_position_falls_back_to_corner(qapp, tmp_path):
    settings = temp_settings(tmp_path)
    settings.setValue("stage/position", QPoint(-50_000, -50_000))

    stage = StageWindow(settings)
    stage.place_in_corner()

    assert stage.pos() != QPoint(-50_000, -50_000)


def test_clouds_hug_the_robot(qapp):
    stage = StageWindow()
    robot = stage.robot.geometry()

    for button in stage.clouds._buttons:
        if button.cloud_id == "settings":
            continue  # sits above the two top clouds
        cloud = button.geometry()
        gap_x = max(robot.left() - cloud.right(), cloud.left() - robot.right(), 0)
        gap_y = max(robot.top() - cloud.bottom(), cloud.top() - robot.bottom(), 0)
        assert gap_x == 0, button.cloud_id  # overlaps the robot's column
        assert gap_y <= 30, button.cloud_id


def test_real_drag_never_clicks(qapp):
    robot = RobotWidget()
    events = []
    robot.clicked.connect(lambda: events.append("click"))
    robot.drag_finished.connect(lambda: events.append("dropped"))

    QTest.mousePress(robot, Qt.MouseButton.LeftButton, pos=QPoint(50, 50))
    QTest.mouseMove(robot, QPoint(80, 70))
    QTest.mouseRelease(robot, Qt.MouseButton.LeftButton, pos=QPoint(80, 70))

    assert events == ["dropped"]


def test_drag_keeps_the_robot_on_screen(qapp, tmp_path):
    stage = StageWindow(temp_settings(tmp_path))
    area = QGuiApplication.primaryScreen().availableGeometry()
    stage.move(area.topLeft())

    stage.robot.drag_started.emit()
    stage.robot.dragged.emit(QPoint(100_000, 100_000))

    assert area.contains(stage.body_rect())


def test_second_click_on_paula_closes_the_clouds(qapp):
    stage = StageWindow()
    stage.show()
    stage.robot.clicked.emit()
    assert stage.clouds.is_open

    center = stage.robot.geometry().center()
    assert stage.childAt(center) is stage.robot  # the clouds overlay is not on top
    QTest.mouseClick(stage.robot, Qt.MouseButton.LeftButton)

    assert not stage.clouds.is_open


def test_chat_stays_on_screen_when_paula_is_top_left(qapp, tmp_path):
    stage = StageWindow(temp_settings(tmp_path))
    area = QGuiApplication.primaryScreen().availableGeometry()
    stage.move(area.topLeft())
    stage.robot.drag_started.emit()
    stage.robot.dragged.emit(QPoint(-1000, -1000))
    assert stage.body_rect().topLeft() == area.topLeft()
    chat = ChatWindow()

    chat.open_next_to(stage)

    assert area.contains(chat.geometry())


def test_every_cloud_is_clickable_at_its_edges(qapp):
    stage = StageWindow()
    stage.show()
    stage.clouds.open_menu()

    for button in stage.clouds._buttons:
        cloud = button.geometry()
        for point in (cloud.topLeft(), cloud.topRight(), cloud.bottomLeft(), cloud.bottomRight()):
            inside = point + QPoint(6 if point.x() == cloud.left() else -6, 0)
            assert not stage.robot.geometry().contains(inside), button.cloud_id


def test_settings_cloud_sits_above_the_top_clouds_inside_the_stage(qapp):
    stage = StageWindow()
    clouds = {b.cloud_id: b.geometry() for b in stage.clouds._buttons}

    settings = clouds["settings"]
    assert stage.rect().contains(settings)
    assert settings.bottom() < min(clouds["chat"].top(), clouds["commands"].top())
    assert not settings.intersects(clouds["chat"]) and not settings.intersects(clouds["commands"])
