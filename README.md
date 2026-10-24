# Paula Port — PC Agent

Runs on the user's PC and starts with Windows. It detects activation (wake word or Ctrl+Shift+P), captures and transcribes audio, plays Paula's voice, shows the robot UI and executes whitelisted commands sent by the hub.

## Layout

```
src/paula_agent/
├── activation/      # wake word, Ctrl+Shift+P hotkey, active window and exclusion list
├── audio/           # capture, Faster-Whisper STT, ElevenLabs TTS, playback
├── ui/
│   ├── robot/       # robot with its six states
│   ├── clouds/      # cloud menu around the robot
│   └── chat/        # chat panel with bubbles and option buttons
├── commands/        # command whitelist and executors
├── messaging/       # RabbitMQ client and message authentication
└── config/
assets/robot/        # one SVG per robot state
prototypes/          # HTML prototypes of the UI (design reference)
tests/               # unit/, integration/
scripts/             # install as a startup service
```

## Robot states

| State | Frame | Accent |
|---|---|---|
| `sleeping` | `#4B5563` | `#22d3ee` |
| `listening` | `#2563EB` | `#22d3ee` |
| `thinking` | `#EA580C` | `#fb923c` |
| `speaking` | `#059669` | `#34d399` |
| `question` | `#7C3AED` | `#c4b5fd` |
| `angry` | `#B91C1C` | `#ef4444` |

Source of truth: `src/paula_agent/ui/robot/states.py` and `assets/robot/*.svg`, both taken from `prototypes/paula_estilos.html`.

## Setup

Requires Python 3.11+, RabbitMQ and Tailscale.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e ".[dev]"
cp .env.example .env            # then fill in the keys
pytest
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md): English only, `main` ← `develop` ← `feat/*` branches, Conventional Commits.
