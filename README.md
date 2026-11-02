# Socra

[![CI](https://github.com/teofurlan/socra/actions/workflows/ci.yml/badge.svg)](https://github.com/teofurlan/socra/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**A local, private voice layer for Claude Code.** Socra turns a Claude Code
session into a spoken conversation: the model talks (Piper TTS), you answer
out loud (faster-whisper STT), and a small web page shows only what the
conversation needs, such as code, permission requests, or the reply. Typing is
always one gesture away.

Everything runs on your machine. The server binds to `127.0.0.1` only; nothing
leaves it except what Claude Code itself sends.

> **Status:** early and Windows-first. Socra is used daily by its author, but
> expect rough edges, breaking changes, and setup steps that are not yet
> automated.

## What it does

Socra has two modes, served by the same local server and page.

| Mode | How you start it | What happens |
|---|---|---|
| **Exam** (`/`) | Claude Code calls Socra's MCP tools | Claude Code runs an oral exam about a project. It speaks each question (optionally showing code), listens to your spoken answer, and gives spoken feedback. |
| **Agent** (`/?mode=agent`) | `socra-server --agent` or the desktop shortcut | A voice-driven coding session in a folder you pick, with Claude Code or Pi as the backend. Replies stream into a timeline, tool use is summarised, and permission requests show Allow / Deny. |

A particle visualizer shows the conversation state at a glance: idle,
listening, thinking, or speaking.

## How it works

```
Claude Code ──MCP (stdio)──▶ socra-server ──WebSocket :8766──▶ page (:8767)
                              │   Piper TTS   ◀── text          │ mic + speakers
                              │   Whisper STT ◀── answer audio ─┘
```

- `server/`: Python process with one asyncio loop for the MCP tools, the
  WebSocket server, and the static page server.
- `web/`: React + Vite page (visualizer, question/code panels, agent timeline).
- `voice/`: the local speech stack and its model files.

When ports 8766/8767 are busy (for example, exam and agent mode at the same
time), a second server binds free ports and its page URL carries them.

## Requirements

- Windows 10/11 (primary target; other platforms are untested)
- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Node.js 22+ and [pnpm](https://pnpm.io/)
- [Claude Code](https://docs.claude.com/en/docs/claude-code), logged in
- A microphone, and Edge or Chrome
- Optional: an NVIDIA GPU with CUDA for faster transcription (CPU works)

## Quick start

```powershell
git clone https://github.com/teofurlan/socra.git
cd socra

# 1. Install the server and build the page
uv sync --project server
pnpm -C web install
pnpm -C web build

# 2. Register Socra as an MCP server for your user (use the absolute path)
claude mcp add --scope user socra -- uv run --project "C:\path\to\socra\server" socra-server
```

The Piper voice (about 115 MB) and the Whisper model (`large-v3-turbo` by
default) download on first use, so the first spoken turn can take a while.
Socra speaks and listens in English, with one voice: LibriTTS-R speaker 0 (US English, Piper).

### Take an exam

Open Claude Code in a project you built and ask for an oral exam, for example:

> Examine me on this project with Socra. Ask me five questions, one at a time.

Claude Code calls `open_page()`, which opens the exam page in an Edge or Chrome
app window, then asks its questions out loud.

### Drive an agent by voice

```powershell
uv run --project server socra-server --agent
```

This opens `http://localhost:8767/?mode=agent`. Pick a folder, choose a backend
and model, and talk. Socra speaks each reply sentence by sentence while it is
written, so the first words sound as soon as the first sentence is complete and
anything said before a tool call is not held back. To get a one-click desktop
shortcut instead:

```powershell
powershell -ExecutionPolicy Bypass -File server\install-shortcut.ps1
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `VOICE_STACK_DIR` | `voice/` | Path to the speech stack (glossary and Whisper cache) |
| `SOCRA_TTS_LENGTH_SCALE` | voice default | Piper speech pace: above 1 is slower |
| `SOCRA_WHISPER_MODEL` | `large-v3-turbo` | faster-whisper model (`base`, `small`, ...) |
| `SOCRA_WHISPER_DEVICE` | `auto` | `auto`, `cuda`, or `cpu` |
| `SOCRA_STT_SAVE_DIR` | unset | Diagnostic: save each spoken turn in a project session as a WAV plus its transcript in this folder |
| `SOCRA_PREFERENCES_FILE` | `%LOCALAPPDATA%/Socra/preferences.json` | Shared page preferences |
| `SOCRA_AGENT_IDLE_S` | `120` | Agent mode exits after this many seconds with no page open |
| `SOCRA_LOG_FILE` | `server/logs/socra.log` | Server log: page connections, agent turns and each step of a mode switch |

See [`server/README.md`](server/README.md) for the MCP tool flow, the
WebSocket protocol, agent backends, and a Whisper benchmark.

## Development

```powershell
# Server tests (no real models are loaded)
uv run --project server pytest -q server/tests

# Web: lint, tests, build (build also typechecks)
pnpm -C web lint
pnpm -C web exec vitest run
pnpm -C web build

# Page dev server with hot reload (start socra-server too, for the WebSocket)
pnpm -C web dev
```

CI runs the same checks on every pull request ([`ci.yml`](.github/workflows/ci.yml)).
Design and product notes live in [`PRODUCT.md`](PRODUCT.md) and
[`DESIGN.md`](DESIGN.md); the web page is described in [`web/README.md`](web/README.md).

## Contributing

Bug reports and ideas are welcome through
[GitHub issues](https://github.com/teofurlan/socra/issues/new/choose). Please
open an issue before starting a large change, so we can agree on the approach
first.

## License

[MIT](LICENSE). Third-party code is listed in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). Voice and speech models are
downloaded from their upstream projects and keep their own licenses.
