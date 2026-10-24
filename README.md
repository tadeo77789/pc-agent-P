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

Requires Windows, Python 3.11+, and the hub with its RabbitMQ running (see the hub README).

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e ".[dev]"
cp .env.example .env            # same AGENT_SHARED_SECRET as the hub
pytest                          # integration tests run when RabbitMQ is reachable
python -m paula_agent           # start the agent
```

On first start it downloads the Whisper model (`small`, about 460 MB) and the Vosk Spanish model (about 40 MB). Until the wake word is ready, Ctrl+Shift+P works.

Start at logon: `powershell -ExecutionPolicy Bypass -File scripts\install-startup.ps1`.

## How it works

- **Activation.** Vosk listens locally with a closed grammar (`paula`, `paula port`) and a confidence threshold. When the foreground app is on the exclusion list, or is fullscreen (a game), the wake word is ignored and only Ctrl+Shift+P works (5 s banner, Esc cancels).
- **Listening.** Only after activation, the mic records one utterance (until about 1 s of silence) and Faster-Whisper transcribes it locally. Nothing is stored.
- **Hub.** The text goes to the hub as a signed `Order`. Replies (`Result`) set the robot state, add a chat bubble and are spoken with ElevenLabs when `speak` is true.
- **Commands.** The hub sends `Action`s; only `open_app` (apps from `config/default_apps.json` or `APPS_FILE`), `system_status` and `shutdown_pc` (needs `confirmed`, 60 s grace, `shutdown /a` cancels) run. Each one reports an `Event`.
- **Clouds.** Abrir chat, Ver comandos (lists the apps), Configuración (opens `.env` in Notepad), Dormir (ignores the wake word until you click Paula; the hotkey still works).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md): English only, `main` ← `develop` ← `feat/*` branches, Conventional Commits.
