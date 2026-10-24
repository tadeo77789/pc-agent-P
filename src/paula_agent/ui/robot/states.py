"""Robot states and palette, taken from prototypes/paula_estilos.html."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parents[4] / "assets" / "robot"


class RobotState(str, Enum):
    """Values match `robot_state` in the hub result message."""

    SLEEPING = "sleeping"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    QUESTION = "question"
    ANGRY = "angry"


@dataclass(frozen=True)
class StateStyle:
    frame: str
    accent: str  # eyes and mouth


STATE_STYLES: dict[RobotState, StateStyle] = {
    RobotState.SLEEPING: StateStyle(frame="#4B5563", accent="#22d3ee"),
    RobotState.LISTENING: StateStyle(frame="#2563EB", accent="#22d3ee"),
    RobotState.THINKING: StateStyle(frame="#EA580C", accent="#fb923c"),
    RobotState.SPEAKING: StateStyle(frame="#059669", accent="#34d399"),
    RobotState.QUESTION: StateStyle(frame="#7C3AED", accent="#c4b5fd"),
    RobotState.ANGRY: StateStyle(frame="#B91C1C", accent="#ef4444"),
}

# Parts shared by every state
BODY = "#1f1f1f"
EARS = "#f5c518"
SCREEN = "#111827"


def svg_path(state: RobotState) -> Path:
    return ASSETS_DIR / f"{state.value}.svg"
