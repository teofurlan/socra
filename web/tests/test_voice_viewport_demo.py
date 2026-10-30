"""Smoke check for voice viewport dev-only demo fixture.

Runs bounded Playwright checks against the running Vite server at port 5174.
Verifies RED on bare production /?mode=agent (zero messages, no scroll overflow),
and GREEN on the simulated fixture /tests/voice-viewport-demo.html (overflowing
timeline, scrolling, simulated typed sends, split code pane open & close, no backend WS/mic).
"""

import os
import unittest
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("SOCRA_TEST_URL", "http://localhost:5174")


class TestVoiceViewportDemo(unittest.TestCase):
    def test_reproduce_bare_page_red(self):
        """Bare page /?mode=agent has zero timeline messages and no overflow."""
        with sync_playwright() as p:
            with p.chromium.launch(channel="chrome") as browser:
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                page.goto(f"{BASE_URL}/?mode=agent")
                page.wait_for_selector("[data-testid=\"orb-visualizer\"]", timeout=5000)

                count = page.locator("li[data-kind=\"reply\"]").count()
                self.assertEqual(count, 0, "Bare page unexpectedly has reply messages")

                overflows = page.evaluate(
                    """() => {
                        const el = document.querySelector(".shell-scroll");
                        return el ? el.scrollHeight > el.clientHeight : false;
                    }"""
                )
                self.assertFalse(overflows, "Bare page unexpectedly overflows")

    def test_fixture_agent_green(self):
        """Fixture page overflows, scrolls, appends on send, and isolates WS/mic."""
        with sync_playwright() as p:
            with p.chromium.launch(channel="chrome") as browser:
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                real_ws = []
                page.on("websocket", lambda ws: real_ws.append(ws.url))

                page.goto(f"{BASE_URL}/tests/voice-viewport-demo.html?mode=agent")
                page.wait_for_selector("[data-testid=\"orb-visualizer\"]", timeout=5000)
                page.wait_for_selector("li[data-kind=\"reply\"]", timeout=5000)

                # 1. Non-zero replies (~40)
                reply_count = page.locator("li[data-kind=\"reply\"]").count()
                self.assertGreaterEqual(reply_count, 40, f"Expected >= 40 replies, found {reply_count}")

                # 2. .shell-scroll genuinely overflows: scrollHeight > clientHeight
                scroller = page.locator(".shell-scroll")
                sh, ch = scroller.evaluate("(el) => [el.scrollHeight, el.clientHeight]")
                self.assertGreater(sh, ch, f"Expected scrollHeight ({sh}) > clientHeight ({ch})")

                # 3. scrollTop moves
                scroller.evaluate("(el) => { el.scrollTop = 200; }")
                st = scroller.evaluate("(el) => el.scrollTop")
                self.assertEqual(st, 200, f"Expected scrollTop 200, got {st}")

                # 4. No backend websocket connection (/ws or /ws/agent)
                for url in real_ws:
                    path = urlparse(url).path
                    self.assertNotIn(path, ("/ws", "/ws/agent"))

                # 5. Typed send appends user message and fake reply
                initial_count = reply_count
                input_el = page.get_by_placeholder("Type instead of speaking")
                input_el.fill("Smoke test message")
                page.keyboard.press("Enter")

                page.wait_for_selector("li[data-kind=\"user\"]", timeout=5000)
                page.wait_for_function(
                    f"() => document.querySelectorAll('li[data-kind=reply]').length > {initial_count}",
                    timeout=5000,
                )
                new_reply_count = page.locator("li[data-kind=\"reply\"]").count()
                self.assertGreater(new_reply_count, initial_count)

    def test_fixture_split_green(self):
        """split=1 opens code pane with code and Close code button closes it."""
        with sync_playwright() as p:
            with p.chromium.launch(channel="chrome") as browser:
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                page.goto(f"{BASE_URL}/tests/voice-viewport-demo.html?mode=agent&split=1")
                page.wait_for_selector("[data-testid=\"orb-visualizer\"]", timeout=5000)
                page.wait_for_selector("li[data-kind=\"reply\"]", timeout=5000)

                # Split is open
                split_attr = page.evaluate("() => document.querySelector('.shell-panels').dataset.split")
                self.assertEqual(split_attr, "true")

                # Close button closes it
                close_btn = page.get_by_role("button", name="Close code")
                self.assertTrue(close_btn.is_visible())
                close_btn.click()

                page.wait_for_function(
                    "() => document.querySelector('.shell-panels').dataset.split === 'false'",
                    timeout=5000,
                )
                split_after = page.evaluate("() => document.querySelector('.shell-panels').dataset.split")
                self.assertEqual(split_after, "false")

    def test_fixture_speaking_query_green(self):
        """state=speaking query parameter sets speaking state in both agent and exam."""
        with sync_playwright() as p:
            with p.chromium.launch(channel="chrome") as browser:
                # 1. Agent mode with state=speaking
                page_agent = browser.new_page(viewport={"width": 1280, "height": 800})
                page_agent.goto(f"{BASE_URL}/tests/voice-viewport-demo.html?mode=agent&state=speaking")
                page_agent.wait_for_selector("[data-testid=\"orb-visualizer\"]", timeout=5000)

                # Expect speaking state indicator in OrbVisualizer data-protocol-state
                agent_state = page_agent.evaluate(
                    "() => document.querySelector('[data-testid=\"orb-visualizer\"]')?.getAttribute('data-protocol-state')"
                )
                self.assertEqual(agent_state, "speaking", f"Expected agent state 'speaking', got '{agent_state}'")

                # 2. Exam mode with state=speaking
                page_exam = browser.new_page(viewport={"width": 1280, "height": 800})
                page_exam.goto(f"{BASE_URL}/tests/voice-viewport-demo.html?mode=exam&state=speaking")
                page_exam.wait_for_selector("[data-testid=\"orb-visualizer\"]", timeout=5000)

                exam_state = page_exam.evaluate(
                    "() => document.querySelector('[data-testid=\"orb-visualizer\"]')?.getAttribute('data-protocol-state')"
                )
                self.assertEqual(exam_state, "speaking", f"Expected exam state 'speaking', got '{exam_state}'")




if __name__ == "__main__":
    unittest.main()
