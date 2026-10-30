# React + TypeScript + Vite

## Layout and theme

Both pages (exam at `/`, agent at `/?mode=agent`) share one console shell: a top bar
(wordmark, Exam/Agent tabs, context chips, connection, the `…` settings menu) over
full-bleed panels. The particle visualizer and state line reside in a non-scrolling
voice stage outside the scroll container, keeping the orb fixed while question or
timeline content scrolls independently below it. The conversation panel also holds
a composer that is always available, so every turn can be typed instead of spoken. In
exam mode a typed answer is sent as the final answer (`answer_text`).

When code arrives (question code, or fenced blocks in an agent reply) a code panel
opens on the right and the conversation narrows, so the particles glide left; on
phones the code panel stacks below. Closing it hides that code until new code arrives.

A narrated walkthrough (`explain` over MCP) replaces the question with the step being
spoken, opens the code panel with that code, and highlights the step's lines when its
audio starts. Back, Repeat, Pause/Resume, Next and Stop buttons steer it; while paused
the microphone listens (or the composer accepts) repeat, back, next, continue or stop.

Settings offer a System/Light/Dark theme; the choice is stored in `socra_theme` and
applied before the first paint by a script in `index.html`. Tokens live in
`src/index.css` (dark on `:root`, light on `:root[data-theme="light"]`).

A neutral dot texture sits behind the orb and conversation in both modes (#4).
Mouse movement produces a small, softly masked drift that settles within 650ms;
there is no background animation loop at rest. It stops when the tab is hidden,
the pointer leaves, or the window loses focus. Reduced motion and touch-only
devices keep the static texture. Theme changes update both layers through CSS.

Long question/transcript text wraps; code preserves whitespace and scrolls inside
its own focusable region. Settings scroll independently when the window is short.

Run `pnpm vitest run`, `pnpm lint`, and `pnpm build` from this directory.
Component tests cover code contents, scroll-container classes, keyboard focus, and
existing re-answer/push-to-talk behavior. jsdom does not measure layout: verify
360px portrait, short landscape, tablet, and desktop sizes in a browser with long
code, unbroken question/transcript text, notices, and settings open. Confirm no
horizontal page/main scroll, internal code scrolling, reachable controls, and
44px targets. Physical touch devices and a native `--app` window still need manual
validation; headless viewport checks cannot establish those platform behaviors.

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend enabling type-aware lint rules by installing `oxlint-tsgolint` and editing `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}
```

See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules) for the full list of rules and categories.

## Development Voice Viewport Demo Fixture

For manual and automated testing of conversation scrolling, code pane split, speaking particle visualizer state, and viewport overflow without needing a running backend, speech model, or microphone, a Vite-served dev-only fixture is available:

- Agent mode (idle): `http://localhost:5174/tests/voice-viewport-demo.html?mode=agent`
- Agent mode (speaking): `http://localhost:5174/tests/voice-viewport-demo.html?mode=agent&state=speaking`
- Agent mode with split code pane: `http://localhost:5174/tests/voice-viewport-demo.html?mode=agent&split=1`
- Agent mode (speaking with split code pane): `http://localhost:5174/tests/voice-viewport-demo.html?mode=agent&state=speaking&split=1`
- Exam mode (idle): `http://localhost:5174/tests/voice-viewport-demo.html?mode=exam`
- Exam mode (speaking): `http://localhost:5174/tests/voice-viewport-demo.html?mode=exam&state=speaking`
- Exam mode with split code pane: `http://localhost:5174/tests/voice-viewport-demo.html?mode=exam&split=1`
- Exam mode (speaking with split code pane): `http://localhost:5174/tests/voice-viewport-demo.html?mode=exam&state=speaking&split=1`

### Fixture Isolation & Behavior
- Directly mounts the real `AgentApp` or `App` components alongside `index.css`.
- Shadows `window.localStorage` in memory before component mount (static ES module imports execute prior to this script running).
- Stubs `navigator.mediaDevices.getUserMedia` to prevent real audio hardware acquisition.
- Intercepts `/ws` and `/ws/agent` WebSocket connections with a mock public protocol handler (preserves Vite HMR socket).
- Supports optional `state=speaking` query param (default `idle`) and handles simulated `interrupt`/`stop` resetting state to `idle`.
- Pre-populates ~40 long replies so `.shell-scroll` genuinely overflows desktop viewports.
- Intercepts typed composer sends to append simulated follow-up replies.
- Visual badge and document title clearly indicate simulated fixture state without altering production layout.
- Smoke test script: `uv run --no-project --with playwright python web/tests/test_voice_viewport_demo.py`
