# socra-server

Local voice exam server. One process, one asyncio loop:

- MCP tools over stdio for Claude Code.
- WebSocket on `ws://localhost:8766/ws` (port 8766).
- Built exam page on `http://localhost:8767/` (port 8767), with static assets and
  an `index.html` fallback for page routes.

Both network listeners bind only to `127.0.0.1`. The page connects to
`ws://localhost:8766` unless its URL carries another port (see below), so it
works the same under the Vite dev server (`pnpm -C web dev`) and when served by
the Python server on 8767.

Each MCP session starts its own `socra-server`. When another Socra already holds
8766 or 8767, the process binds free ports instead, and its page URL carries the
WebSocket port, for example `http://localhost:51000/?ws=51001`. `open_page()`
opens that URL, so every session's page connects back to its own process.
When that process exits, its page retries a few times and then shows
"Session ended, close this window" instead of waiting forever. If the page
servers cannot start at all, the MCP tools keep working and report `no_client`
with an `error` and no URL, never another session's page.

Because a page on free ports has a new origin each session, page preferences
(voice, turn mode, theme, visualizer, agent choice and folder, and the rest of
the settings) are not left to that origin's `localStorage` alone. Every server
keeps them in one file, `%LOCALAPPDATA%/Socra/preferences.json` (override with
`SOCRA_PREFERENCES_FILE`), served on the page's own origin at
`/api/preferences`: the page loads it before its first render and sends each
change back. Only the page's own origin may write to it. The microphone choice
stays per origin, since browsers give each origin its own device ids.

---

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) installed
- The voice stack checked out at `voice/` in this
  repo (or set `VOICE_STACK_DIR` to the absolute path), for the English-terms
  glossary (`pi_voice/terms.json`) and the Whisper model cache under `models/whisper/`.
- The Piper voice (`es_AR-daniela-high`, about 115 MB) downloads from Hugging Face
  (`rhasspy/piper-voices`) on first use and is cached.
- Run `uv sync --project server` to install server and speech dependencies.

---

## Build and register with Claude Code

From the repository root, build the page once (and again after web changes):

```bash
pnpm -C web build
```

Register the MCP server for your user, replacing `<abs path>` with the absolute
path to this repository. Quote the path if it contains spaces:

```bash
claude mcp add --scope user socra -- uv run --project "<abs path>/server" socra-server
```

An exam session calls `open_page()` first. If no page is connected, it opens a
visible Edge app window, then tries Chrome, then the default browser. It waits
at most 15 seconds for a connection. All `no_client` responses point to this
process's page, `http://localhost:8767/` unless those ports were busy; if the
page has not been built, they also include `"hint":"run pnpm -C web build"`.

## Run

```bash
# From the repo root (socra/); Claude Code normally starts this via MCP.
uv run --project server socra-server
```

Or from inside `server/`:

```bash
uv run socra-server
```

The MCP handshake is instant; the Piper and Whisper models load lazily in a
background thread so the first `say`/`ask` call may take a few
seconds (or longer on a cold model cache). Whisper retries inference on CPU
if CUDA initializes but its runtime libraries are unavailable. Transcription
failures are logged, not returned as fabricated empty answers.

Only MCP JSON-RPC uses stdout. Python prints, library warnings and native
speech-library stdout are redirected to stderr before model loading.

### Agent mode

Agent mode drives an agent by voice in a folder you choose. Two backends are
available: Claude Code (through the Claude Agent SDK) and Pi (`pi --mode rpc`,
with your gentle-pi extensions and your GPT, Gemini or other Pi providers).
Start it without an MCP client:

```bash
uv run --project server socra-server --agent
```

This runs the HTTP and WebSocket servers without MCP stdio and opens
`http://localhost:8767/?mode=agent`. If Socra is already running (for example
as the exam MCP server), it only opens the page. The page talks to
`ws://localhost:8766/ws/agent`; the exam keeps using `/ws`.

- The folder is chosen with the native OS dialog, which the server opens:
  browsers never hand a page an absolute path.
- Starting opens the chat immediately while the selected backend initializes;
  startup alone leaves the composer idle. One typed or transcribed audio turn
  can be queued during startup and is sent once the session is ready; additional
  turns are refused with a notice. If
  startup fails, the page receives an error and an idle state, and can retry
  without losing its visible user message. Interrupting during startup cancels
  that pending session; late provider completions are closed and ignored.
- Tool calls follow your Claude Code permission settings. Only calls those
  settings mark as "ask" show Allow / Deny on the page; with
  `defaultMode: bypassPermissions` nothing asks.
- Claude Code must be logged in (`claude auth login`); the page shows the
  backend as not configured otherwise.
- **Modes.** A project session has a mode: agent, mentor or exam. Pick one in
  the prompt bar (next to the folder and model), or ask for it by voice: the
  agent calls Socra's `switch_mode` tool and the page asks you to confirm, so a
  misheard phrase never switches. Mentor is a read-only explainer placeholder
  (the real mentor instructions belong to issue #18); in exam mode the agent
  asks spoken questions and records each verdict with `record_exam_result`.
  The MCP-driven exam on `/` is unchanged. Modes need Claude Code: on Pi the
  selector is disabled and a switch request is refused.
- **Handoff.** A switch does not resume the session (that would keep the old
  system prompt and an ever-growing context). Socra asks the outgoing agent for
  a JSON summary (`goal`, `decisions`, `open_items`, `user_doubts`), asks again
  up to twice if a field is missing, and aborts with an error, staying in the
  current mode, if it still is not valid. It then opens a new session in the new
  mode before closing the old one, so a failed start loses nothing. The new
  session is seeded with what Socra recorded itself (files changed, tools
  used, permission decisions, exam results), the summary and the last 4 turns
  verbatim (replies capped at about 1,500 characters). It says one spoken
  sentence of what it understood, which you can correct, and can call
  `search_transcript` for details from the previous session. The timeline
  continues across the switch with a "Context condensed" marker.
- **Transcripts.** Socra keeps its own JSONL transcript per session under
  `%LOCALAPPDATA%\Socra\sessions\<project-hash>\` (`~/.cache/Socra/sessions` on
  other systems) and deletes files older than 30 days when the server starts.
- Pi is found on `PATH` or in `~/.pi/agent/bin`. Its model list shows the
  models of every provider Pi is logged in to (`/login` inside `pi`), in
  Pi's order; Pi's default provider is not preferred, and the session always
  starts with the provider and model you pick. The first list skips Pi's
  extensions (about 1 s); a background refresh with extensions (about 20 s)
  adds the providers they bring, such as Antigravity, and is saved in
  `%LOCALAPPDATA%\Socra\pi-models.json` (`~/.cache/Socra` elsewhere) so the
  next start shows them at once. Reload the page to see them the first time.
  Starting a Pi session loads your extensions and can take up to a minute.
- Pi does not ask before tool calls by itself; it follows its own settings
  (gentle-pi's Normal / Auto / YOLO mode). When an extension asks for a
  confirmation, such as gentle-pi before a recognized data-loss command, the
  page shows Allow / Deny. Pi questions that need a choice or free text are
  cancelled, since they cannot be answered by voice yet.

For a one-click desktop shortcut (Windows):

```powershell
powershell -ExecutionPolicy Bypass -File server\install-shortcut.ps1
# Remove it again:
powershell -ExecutionPolicy Bypass -File server\install-shortcut.ps1 -Remove
```

The shortcut runs `.venv\Scripts\pythonw.exe -m socra_server --agent` with no
console window; anything the server prints goes to `server/logs/socra-agent.log`.
Agent mode stops by itself once no agent page has been open for two minutes
(`SOCRA_AGENT_IDLE_S`), which frees ports 8766 and 8767. An exam MCP server
that starts while agent mode holds those ports serves its page on free ports
instead, so exam and agent mode can run at the same time.

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `VOICE_STACK_DIR` | `voice/` (relative to repo root) | Absolute path to the voice stack directory |
| `SOCRA_TTS_LENGTH_SCALE` | voice default (`1.2` for Daniela) | Piper speech pace: above 1 is slower, below 1 faster |
| `SOCRA_WHISPER_MODEL` | `large-v3-turbo` | Faster-whisper model (`base`, `small`, `large-v3-turbo`, etc.) |
| `SOCRA_WHISPER_DEVICE` | `auto` | Execution device: `auto` (CUDA float16 if available, else CPU int8), `cuda`, or `cpu` |
| `SOCRA_PREFERENCES_FILE` | `%LOCALAPPDATA%/Socra/preferences.json` | Page preferences shared by every server process |
| `SOCRA_AGENT_IDLE_S` | `120` | Agent mode exits after this many seconds without an agent page |

### Whisper Model Benchmark (RTX 4060 8 GB)

Benchmark of Spanish answer transcription using Kokoro-synthesized audio:
- **A1** (3.09s): *"El río más largo de Sudamérica es el Amazonas."*
- **A2** (4.24s): *"No recuerdo bien, pero creo que fue en mil cuatrocientos noventa y dos."*

| Model | Device | Load Time (cached) | A1 Time | A1 Transcript | A2 Time | A2 Transcript |
|---|---|---|---|---|---|---|
| `base` | cuda (float16) | 1.86 s | 0.60 s | "El río más largo de Sudamérica es el Amazonas." | 0.15 s | "No recuerdo bien, pero creo que fue en 1492." |
| `small` | cuda (float16) | 1.24 s | 0.30 s | "El río más largo de Sudamérica es el Amazonas." | 0.26 s | "No recuerdo bien, pero creo que fue en 1492." |
| `large-v3-turbo` | cuda (float16) | 4.35 s | 0.55 s | "El río más largo de Sudamérica es el Amazonas." | 0.43 s | "No recuerdo bien, pero creo que fue en 1492." |

**Chosen default: `large-v3-turbo`**.
All models comfortably beat the <= 3.0 s transcription budget on the RTX 4060 (taking <= 0.6 s for ~5 s of audio). `large-v3-turbo` provides the highest recognition accuracy and robustness against accents/slang, while executing in ~0.5 s.

---

## Tests

```bash
uv run --project server pytest -q server/tests
```

No real models are loaded during tests — all adapters use in-process fakes.

### Manual real-model smokes

```bash
# Strict MCP + WebSocket round trip; requires free ports 8766 and 8767.
pnpm -C web build
uv run --project server python server/tests/smoke_e2e.py

# Adapter-only round trip.
uv run --project server python server/tests/smoke_roundtrip.py
```

The strict smoke starts its own server, reuses a headless WebSocket client
without opening a browser or microphone, checks display-only question code,
and polls a real Piper-generated answer through Whisper and MCP. It prints
its transcript and timings and fails on protocol contamination or missing tools.

This standalone script is excluded from default pytest collection. It loads the
real adapters, synthesizes the Spanish process/thread sentence, transcribes the
WAV without a cleaner, and prints the transcript, WAV duration and timings.
An empty transcript fails the smoke. Initial model loading may access the
Whisper cache or download missing model files.

---

## `.mcp.json` snippet for Claude Code

To enable Socra for one project only, add this to that project's `.mcp.json`
instead of the user-scope `claude mcp add` above, replacing `<abs-path>` with
the absolute path to this repo's root:

```json
{
  "mcpServers": {
    "socra": {
      "command": "uv",
      "args": ["run", "--project", "<abs-path>/server", "socra-server"]
    }
  }
}
```

---

## Architecture

```
socra_server/
├── domain/                   # Pure types and rules, no I/O
│   ├── session.py            # ExamSession state
│   ├── agent.py              # Agent mode types (backends, models, events)
│   ├── modes.py              # Agent, mentor and exam: instructions and tools
│   ├── handoff.py            # Summary template, recorded facts, seed for a mode switch
│   ├── speakable.py          # Markdown reply -> text worth speaking
│   └── voices.py             # Voice catalogue
├── adapters/
│   ├── piper_tts.py          # Piper voice, English glossary terms as phonemes (lazy load)
│   ├── whisper_stt.py        # Wraps dictation.transcriber.WhisperTranscriber (lazy load)
│   ├── claude_code_agent.py  # AgentBackend over the Claude Agent SDK
│   ├── pi_agent.py           # AgentBackend over `pi --mode rpc`
│   ├── tool_summary.py       # One-line tool call summaries for both agents
│   ├── transcript_store.py   # Session transcripts (JSONL), search, 30-day retention
│   ├── browser.py            # Opens the page in an Edge/Chrome app window
│   ├── folder_dialog.py      # Native folder picker for agent mode
│   └── preferences_file.py   # Shared preferences.json store
├── entrypoints/
│   ├── mcp_tools.py          # open_page, say, ask, get_answer, finish
│   ├── http_server.py        # Built page and /api/preferences on 127.0.0.1:8767
│   └── ws_server.py          # WebSocket routes /ws (exam) and /ws/agent
├── app.py                    # ExamApp: ties session + ports + PageChannel
├── agent_app.py              # AgentApp: drives an agent by voice
├── agent_registry.py         # Which agent backends exist and what a selection means
├── socra_tools.py            # Socra's own agent tools (switch_mode, search_transcript, ...)
├── ports.py                  # Speech, agent and channel protocols
└── __main__.py               # One asyncio loop for MCP, WebSocket and HTTP
```

### MCP exam flow

1. `open_page()` returns `connected` or `no_client` (with the URL/build hint).
2. `say(text)` speaks instructions or feedback; it does not begin listening.
3. `ask(question, index, total, glossary=None, code=None)` shows the numbered
   question, speaks only `question`, and begins listening. Put code snippets in
   `code`, not in the spoken text. `glossary` supplies optional STT term hints.
4. Call `get_answer(wait_s=20)` **repeatedly while it returns `listening`**.
   Each call waits 1–25 seconds. `answered` includes `index` and `text`: the
   verbatim transcript, never cleaned or rewritten. Preserve it as received.
5. `finish(summary=None)` optionally speaks a summary, then sends idle and
   finished. The page replaces the question panel with **Exam finished**.

Speech tools `say()` and `ask()` wait for browser playback (`playback_done`) with timeout = WAV duration + 2 s before returning or transitioning to `listening`.

### WebSocket protocol

**Server → page**

| Message | Fields |
|---|---|
| `state` | `state`: `"idle"` \| `"speaking"` \| `"listening"` \| `"thinking"` |
| `question` | `index`, `total`, `text`, optional display-only `code` |
| `tts_audio` | `format: "wav"`, `data: <base64>` |
| `transcript` | `text`, `final: true` |
| `notice` | `text`: temporary notice (e.g. non-answer rejection) |
| `voices` | `voices`: `[{id, label}]`, `current`: selected voice id |
| `finished` | No fields; sent after `state: idle` |

**Page → server**

| Message | Fields |
|---|---|
| `answer_audio` | `format: "wav"`, `data: <base64>` |
| `answer_text` | `text`: a typed answer, sent as the final answer |
| `playback_done` | Sent when `tts_audio` playback completes or fails |
| `reanswer` | _(none)_ |
| `mode` | `mode`: `"auto"` \| `"push-to-talk"` |
| `voice` | optional `voice`: voice id to select; the server answers with `voices` |

The agent route `/ws/agent` accepts `agent_hello`, `pick_folder`,
`start_agent` (optional `mode`), `turn_text`, `turn_audio`, `permission_response`,
`interrupt`, `playback_done`, `voice`, `switch_mode` (`mode`) and
`mode_switch_response` (`mode`, `allow`); the server answers a switch with
`agent_switching`, `agent_mode_changed`, `mode_switch_request`,
`mode_switch_closed` and `mode_switch_failed`. See `entrypoints/ws_server.py` for its fields.
