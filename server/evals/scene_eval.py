"""Manual scene-guide eval against a real Claude Code session; not collected by pytest.

Each prompt runs in a fresh mentor-mode ClaudeCodeBackend session (cwd = the Socra repo
root) with a fake page: ``present`` validates with ``parse_scene`` and answers with the
same JSON shapes as the app. Pass = a valid scene on the 1st or 2nd ``present`` call.
It spends subscription tokens (10 sessions). Run from the repository root:
    uv run --project server python server/evals/scene_eval.py [--only 1,3] [--model sonnet]
    uv run --project server python server/evals/scene_eval.py --self-test   # offline, no model
Results: a Markdown table on stdout and a JSON file under .impeccable/review/scene-eval/.
"""
from __future__ import annotations

import argparse
import asyncio
import dataclasses
import json
import sys
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from socra_server.adapters.claude_code_agent import ClaudeCodeBackend
from socra_server.domain.agent import AgentError, PermissionRequest, ReplyDone, ToolActivity
from socra_server.domain.modes import get_mode
from socra_server.domain.scene import parse_scene
from socra_server.socra_tools import CallbackToolbox
from socra_server.walkthrough import COMPLETED_NOTE

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / ".impeccable" / "review" / "scene-eval"
DEFAULT_MODEL = "sonnet"
PASS_WITHIN = 2  # a valid scene on the 1st or 2nd present call
READ_ONLY_TOOLS = frozenset({"Read", "Grep", "Glob", "LS", "NotebookRead", "TodoWrite"})

PROMPTS: tuple[tuple[str, str], ...] = (
    ("project", "Explain how the voice pipeline works in this project, from the microphone to the spoken reply."),
    ("project", "Explain how a scene is validated and played in this project."),
    ("project", "Explain how mode switching works in this project."),
    ("project", "Explain how the particle field draws a diagram highlight in this project."),
    ("project", "Explain how the transcript search works in this project."),
    ("concept", "Explain hash map collisions."),
    ("concept", "Explain how a stack works, with push and pop."),
    ("concept", "Explain how inserting into a binary search tree works."),
    ("concept", "Explain the difference between a queue and a stack."),
    ("concept", "Explain how an HTTP request reaches a database through a cache."),
)
HASH_MAP_PROMPT = 6  # 1-based; its valid scene must use `structure` (S8)


@dataclasses.dataclass
class Row:
    n: int
    kind: str
    prompt: str
    present_calls: int = 0
    valid_attempt: int | None = None  # which present call (1-based) was the first valid one
    primitives: list[str] = dataclasses.field(default_factory=list)
    steps: int = 0
    scene_guide_called: bool = False
    elapsed_s: float = 0.0
    passed: bool = False
    structure_ok: bool | None = None  # only for the hash map prompt
    errors: list[list[dict]] = dataclasses.field(default_factory=list)  # per invalid call
    turn_error: str = ""
    tools: list[str] = dataclasses.field(default_factory=list)


class FakePage:
    """The page side of ``present``: same JSON answers as the app's ``_tool_present``."""

    def __init__(self, row: Row) -> None:
        self.row = row

    async def play(self, raw: Any) -> str:
        self.row.present_calls += 1
        scene, errors = parse_scene(raw)
        if scene is None:
            self.row.errors.append(errors)
            return json.dumps({"status": "invalid", "errors": errors})
        if self.row.valid_attempt is None:
            self.row.valid_attempt = self.row.present_calls
            self.row.primitives = sorted({o.primitive for o in scene.objects})
            self.row.steps = len(scene.steps)
        return json.dumps({"status": "completed", "steps": len(scene.steps), "note": COMPLETED_NOTE})


async def _unused(*_: Any) -> Any:
    raise RuntimeError("not available in the eval")


def toolbox_for(page: FakePage) -> CallbackToolbox:
    return CallbackToolbox(switch=_unused, record=_unused, search=_unused, play=page.play, clear=_unused)


async def read_only(request: PermissionRequest) -> bool:
    return request.tool in READ_ONLY_TOOLS


def finish(row: Row) -> Row:
    row.passed = row.valid_attempt is not None and row.valid_attempt <= PASS_WITHIN
    if row.n == HASH_MAP_PROMPT:
        row.structure_ok = row.valid_attempt is not None and "structure" in row.primitives
    return row


async def run_prompt(backend: ClaudeCodeBackend, model: str, n: int, kind: str, prompt: str) -> Row:
    row = Row(n, kind, prompt)
    page = FakePage(row)
    started = perf_counter()
    conversation = None
    try:
        conversation = await backend.open(
            model, REPO_ROOT, read_only, mode=get_mode("mentor"), toolbox=toolbox_for(page)
        )
        async for event in conversation.send(prompt):
            if isinstance(event, ToolActivity):
                row.tools.append(event.tool)
                if "scene_guide" in event.tool:
                    row.scene_guide_called = True
            elif isinstance(event, AgentError):
                row.turn_error = event.message
            elif isinstance(event, ReplyDone):
                break
    except Exception as exc:  # one broken session must not lose the other rows
        row.turn_error = f"{type(exc).__name__}: {exc}"
    finally:
        if conversation is not None:
            try:
                await conversation.close()
            except Exception as exc:
                row.turn_error = row.turn_error or f"close failed: {exc}"
    row.elapsed_s = round(perf_counter() - started, 1)
    return finish(row)


def table(rows: list[Row]) -> str:
    lines = [
        "| # | kind | present calls | valid on | primitives | steps | scene_guide | secs | pass |",
        "|---|------|---------------|----------|------------|-------|-------------|------|------|",
    ]
    for r in rows:
        lines.append(
            f"| {r.n} | {r.kind} | {r.present_calls} | {r.valid_attempt or '-'} "
            f"| {', '.join(r.primitives) or '-'} | {r.steps or '-'} "
            f"| {'yes' if r.scene_guide_called else 'no'} | {r.elapsed_s} | {'PASS' if r.passed else 'FAIL'} |"
        )
    passed = sum(r.passed for r in rows)
    lines.append(f"\n{passed}/{len(rows)} passed (valid scene within {PASS_WITHIN} present calls).")
    hash_row = next((r for r in rows if r.n == HASH_MAP_PROMPT), None)
    if hash_row is not None:
        lines.append(f"Hash map prompt uses `structure`: {hash_row.structure_ok}.")
    for r in rows:
        if r.turn_error:
            lines.append(f"Prompt {r.n} turn error: {r.turn_error}")
    return "\n".join(lines)


def save(rows: list[Row], model: str) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"scene-eval-{datetime.now():%Y%m%d-%H%M%S}.json"
    payload = {
        "model": model,
        "passed": sum(r.passed for r in rows),
        "total": len(rows),
        "rows": [dataclasses.asdict(r) for r in rows],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def parse_only(text: str | None) -> list[int]:
    if not text:
        return list(range(1, len(PROMPTS) + 1))
    chosen = sorted({int(part) for part in text.split(",") if part.strip()})
    bad = [i for i in chosen if not 1 <= i <= len(PROMPTS)]
    if bad:
        raise SystemExit(f"--only takes numbers from 1 to {len(PROMPTS)}; got {bad}")
    return chosen


async def self_test() -> int:
    """Offline: feed one invalid and one valid scene to the fake page; no model involved."""
    valid = {
        "version": 1,
        "title": "Adding two numbers",
        "objects": [{"id": "src", "primitive": "code", "params": {"code": "a = 1\nb = 2", "language": "python"}}],
        "steps": [{"id": "intro", "say": "Two names hold numbers."}, {"id": "end", "say": "That is all."}],
        "cues": [{"at": "intro", "do": [{"object": "src", "action": "focus", "params": {"lines": [1, 2]}}]}],
    }
    row = Row(HASH_MAP_PROMPT, "concept", "self-test")
    page = FakePage(row)
    answers = [await page.play({"version": 1}), await page.play(valid)]
    finish(row)
    for answer in answers:
        print(answer[:160])
    print(table([row]))
    ok = (
        json.loads(answers[0])["status"] == "invalid"
        and json.loads(answers[1])["status"] == "completed"
        and row.passed
        and row.valid_attempt == 2
        and row.structure_ok is False
        and not await read_only(PermissionRequest("1", "Bash", "x"))
        and await read_only(PermissionRequest("2", "Read", "x"))
    )
    print("self-test:", "ok" if ok else "FAILED")
    return 0 if ok else 1


async def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Scene-guide eval with a real Claude Code session per prompt.")
    parser.add_argument("--only", help="comma-separated prompt numbers to run, e.g. 1,6 (default: all 10)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Claude Code model (default: {DEFAULT_MODEL})")
    parser.add_argument("--self-test", action="store_true", help="offline check of the fake page; no model")
    args = parser.parse_args(argv)
    if args.self_test:
        return await self_test()
    selected = parse_only(args.only)
    backend = ClaudeCodeBackend()
    status = await backend.check()
    if not status.ready:
        print(f"Claude Code is not ready: {status.message}", file=sys.stderr)
        return 2
    rows: list[Row] = []
    for n in selected:
        kind, prompt = PROMPTS[n - 1]
        print(f"[{n}/{len(PROMPTS)}] {prompt}", file=sys.stderr, flush=True)
        rows.append(await run_prompt(backend, args.model, n, kind, prompt))
    print(table(rows))
    print(f"\nSaved {save(rows, args.model)}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
