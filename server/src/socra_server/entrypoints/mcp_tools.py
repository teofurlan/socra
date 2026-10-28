"""MCP exam tools over stdio; stdout is reserved for JSON-RPC."""
from __future__ import annotations

import logging
import sys

from mcp.server.fastmcp import FastMCP

from socra_server.domain.scene import PRESENT_PURPOSE, SCENE_GUIDE

logging.basicConfig(stream=sys.stderr, level=logging.DEBUG, format="%(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# The shared application is injected by __main__ before the server starts.
_app = None


def get_app():
    """Return the shared ExamApp; raises if not yet wired."""
    if _app is None:
        raise RuntimeError("ExamApp not wired — call wire_app() first")
    return _app


def wire_app(app) -> None:
    """Wire the shared ExamApp into this entrypoint."""
    global _app
    _app = app


def create_mcp() -> FastMCP:
    """Build the MCP interface that an exam session uses to drive the page."""
    mcp = FastMCP(
        "socra-server",
        instructions=(
            "Local oral exam tools. Start with open_page(). Use say() for spoken feedback, "
            "ask() for questions with optional display-only code, explain() to narrate code while the page highlights the lines being discussed, present() to narrate a scene whose visuals change step by step, and call get_answer() "
            "repeatedly while it returns listening. Answers are verbatim transcripts, "
            "not cleaned or rewritten. End with finish()."
        ),
    )

    @mcp.tool()
    async def open_page() -> dict:
        """Use before starting an exam, or after any tool returns no_client.

        Reuse an already-connected page without launching a browser. Otherwise
        open a visible Edge/Chrome app window (default browser as fallback) and
        wait at most 15 seconds total for the page to connect. Returns status
        connected, or no_client with the page URL and a build hint if needed
        (or with an error and no URL if the page servers could not start).
        """
        return await get_app().open_page()

    @mcp.tool()
    async def say(text: str) -> dict:
        """Use for instructions or feedback that should be spoken, not a question.

        Sends state:speaking and synthesized WAV audio; does not start listening
        or wait for browser playback. Returns status ok, or no_client with a URL.
        """
        return await get_app().say(text)

    @mcp.tool()
    async def ask(
        question: str,
        index: int,
        total: int,
        glossary: list[str] | None = None,
        code: str | None = None,
    ) -> dict:
        """Use to pose each numbered exam question and begin listening.

        question contains only spoken text. Put code-reading snippets in code:
        they are displayed verbatim on the page and are NEVER synthesized.
        glossary optionally supplies domain terms as Whisper initial_prompt hints.
        Sends the question, speech audio, then listening state. Returns status
        asked or no_client with a URL. Next, poll get_answer repeatedly while its
        status is listening; answers are verbatim transcripts, never cleaned.
        """
        return await get_app().ask(question, index, total, glossary, code)

    @mcp.tool()
    async def explain(code: str, language: str = "", steps: list[dict] | None = None) -> dict:
        """Use to explain code out loud while the page highlights the lines being discussed.

        code is shown verbatim in the code panel; language (e.g. "python") only
        affects syntax colours. steps is an ordered list of
        {"say": "spoken explanation", "focus": {"lines": [start, end]}}: lines
        are 1-based and inclusive, and focus may be omitted for a step that
        highlights nothing. Each step is spoken separately and its lines are
        highlighted when its audio starts. Blocks until the walkthrough ends;
        the user may pause, repeat, go back, skip or stop meanwhile.
        Returns completed (steps), stopped (step, total: the user ended it),
        invalid (errors: one per bad step with step, field and message; nothing
        was shown, fix the steps and call again), busy, page_disconnected, error (message), or
        no_client with a URL.
        """
        return await get_app().explain(code, language, steps)

    @mcp.tool(description=f"{PRESENT_PURPOSE} {SCENE_GUIDE} Also no_client with a URL when no page is open.")
    async def present(scene: dict) -> dict:
        return await get_app().present(scene)

    @mcp.tool()
    async def get_answer(wait_s: float = 20) -> dict:
        """Use after ask to retrieve the student's verbatim spoken transcript.

        Waits up to wait_s seconds (clamped to 1–25). Call repeatedly while the
        result is {"status":"listening"}; that means no final answer yet, not an
        error. On {"status":"answered","index":n,"text":...}, text is the
        verbatim STT transcript, never cleaned, paraphrased or rewritten. Preserve
        it as received. A no_client result includes the URL; reconnect the page.
        """
        return await get_app().get_answer(wait_s)

    @mcp.tool()
    async def finish(summary: str | None = None) -> dict:
        """Use once the exam is complete, after grading the last answer.

        Optionally speak summary, then send idle and the question-less finished
        screen. Does not wait for browser audio playback. Returns status finished
        or no_client with a URL. Do not keep polling get_answer after finishing.
        """
        return await get_app().finish(summary)

    return mcp
