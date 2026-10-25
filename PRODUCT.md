# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

One developer who works with Claude Code all day, seated at a desk next to their editor, in long sessions. They use Socra to talk to Claude Code instead of typing: to be examined on a project they built, or to drive a coding session by voice.

## Product Purpose

Socra is a local, private voice layer for Claude Code. It turns a Claude Code session into a spoken conversation: the model speaks (Piper TTS), the user answers out loud (Whisper STT), and the page shows what the conversation needs to show. Success is a conversation that feels natural enough that the user stops reaching for the keyboard, while typing stays one gesture away.

## Positioning

Speaking and listening replace typing for a coding agent, on the user's own machine. The particle visualizer is the face of the conversation: it shows who is talking (Socra speaking, the user being heard, the model thinking) at a glance.

## Operating Context

- Exam mode (`/`): Claude Code runs an oral exam about a project through Socra's MCP tools. It speaks each question, can show display-only code with it, listens to the spoken answer, and gives spoken feedback.
- Agent mode (`?mode=agent`): a voice-driven Claude Code session inside a folder the user picks. Replies stream into a timeline, tool use is summarised, and permission requests appear on the page with Allow/Deny. The user can also type a turn. The session can switch between agent, mentor and exam modes from the prompt bar or by voice (confirmed on screen); each switch starts a new session seeded with a handoff of what happened.
- Opened from a desktop shortcut or by the MCP server in a local browser window, usually beside the editor.

## Capabilities and Constraints

- Local only: the server binds 127.0.0.1 (WebSocket 8766, page 8767). Nothing leaves the machine except what Claude Code itself sends.
- Windows is the primary environment.
- UI copy is in English.
- States the page must always make legible: idle, listening, thinking, speaking, plus connection state.
- Visualizer looks: Lines (default), Letters, and Letters on a grid. The ElevenLabs shader orb is retired.
- Exam mode must keep working unchanged in behavior while its look changes.

## Brand Commitments

- Name: Socra.
- The particle field (particles drift loose when idle and gather into a rotating sphere around a voice) is the identity's centrepiece, chosen by the user.

## Evidence on Hand

- Particle study: `web/public/studies/particle-study.html`.
- No testimonials, users, metrics, or press exist; do not invent them.

## Product Principles

1. Voice first, keyboard always available.
2. The conversation state is always legible from across the desk.
3. Show only what the spoken conversation needs: code, permissions, the reply.
4. Private and local by construction.
