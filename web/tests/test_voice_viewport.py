"""Voice viewport regression against the running web app (requires Chrome).

Run Vite on port 5174, then:
  uv run --no-project --with playwright python web/tests/test_voice_viewport.py
Uses isolated browser contexts and the public WebSocket protocol; no Socra server,
agent, microphone, or stored user data is used.
"""

import os
import unittest

from playwright.sync_api import sync_playwright


BASE_URL = os.environ.get("SOCRA_TEST_URL", "http://localhost:5174")
SIZES = ((1440, 900), (768, 1024), (360, 640), (667, 375))
SOCKET = """
localStorage.setItem('socra_mode', 'push-to-talk');
window.testSockets = [];
window.WebSocket = class {
  static OPEN = 1;
  readyState = 1;
  constructor() {
    window.testSockets.push(this);
    setTimeout(() => this.onopen?.(new Event('open')), 0);
  }
  send() {}
  close() {}
  receive(data) { this.onmessage?.({data: JSON.stringify(data)}); }
};
"""


class VoiceViewportTest(unittest.TestCase):
    def test_voice_stays_visible_while_content_scrolls_and_code_opens(self):
        with sync_playwright() as playwright:
            with playwright.chromium.launch(channel="chrome") as browser:
                for mode in ("agent", "exam"):
                    for theme in ("dark", "light"):
                        for width, height in SIZES:
                            with self.subTest(mode=mode, theme=theme, size=(width, height)):
                                context = browser.new_context(viewport={"width": width, "height": height})
                                context.add_init_script(SOCKET + f"localStorage.setItem('socra_theme', '{theme}');")
                                page = context.new_page()
                                try:
                                    page.goto(f"{BASE_URL}/?mode={mode}")
                                    page.get_by_test_id("orb-visualizer").wait_for()
                                    page.wait_for_function("window.testSockets.some(s => s.onmessage)")
                                    page.evaluate("""mode => {
                                      const ws = window.testSockets.find(s => s.onmessage);
                                      if (mode === 'agent') {
                                        ws.receive({type: 'agent_started', backend: 'claude-code', model: 'sonnet', cwd: 'C:/test'});
                                        for (let i = 0; i < 40; i++) {
                                          ws.receive({type: 'agent_reply', text: `Reply ${i}: ` + 'Long conversation. '.repeat(30)});
                                        }
                                      } else {
                                        ws.receive({type: 'question', index: 1, total: 1, text: 'Long question. '.repeat(500)});
                                      }
                                      ws.receive({type: 'state', state: 'speaking'});
                                    }""", mode)
                                    for split in (False, True):
                                        if split:
                                            page.evaluate("""mode => {
                                              const ws = window.testSockets.find(s => s.onmessage);
                                              const code = 'print(42)\\n'.repeat(100);
                                              ws.receive(mode === 'agent'
                                                ? {type: 'agent_reply', text: 'Shown code:\\n```python\\n' + code + '```'}
                                                : {type: 'question', index: 1, total: 1, text: 'Long question. '.repeat(500), code});
                                            }""", mode)
                                            page.wait_for_function("document.querySelector('.shell-panels').dataset.split === 'true'")
                                        # Wait for the actual split animation and font layout, not a fixed sleep.
                                        page.evaluate("async () => { await document.fonts.ready; await Promise.all(document.getAnimations().filter(a => a.effect?.getTiming().iterations !== Infinity).map(a => a.finished)); }")
                                        scroller = page.locator(".shell-scroll")
                                        self.assertTrue(scroller.evaluate("el => el.scrollHeight > el.clientHeight && el.clientHeight > 20"))
                                        for fraction in (0, 0.5, 1):
                                            scroller.evaluate("(el, f) => { el.scrollTop = (el.scrollHeight - el.clientHeight) * f; }", fraction)
                                            page.evaluate("() => new Promise(requestAnimationFrame)")
                                            orb = page.get_by_test_id("particle-visualizer").bounding_box()
                                            state = page.get_by_test_id("state-label").bounding_box()
                                            composer = page.locator(".composer-dock").bounding_box()
                                            header = page.locator(".shell-panels > .panel > .panel-head").bounding_box()
                                            with self.subTest(split=split, scroll=fraction):
                                                self.assertGreater(orb["width"], 0)
                                                self.assertGreaterEqual(orb["x"], 0)
                                                self.assertLessEqual(orb["x"] + orb["width"], width)
                                                self.assertGreaterEqual(orb["y"], header["y"] + header["height"])
                                                self.assertLessEqual(orb["y"] + orb["height"], composer["y"])
                                                self.assertGreaterEqual(state["y"], 0)
                                                self.assertLessEqual(state["y"] + state["height"], composer["y"])
                                                self.assertLessEqual(composer["y"] + composer["height"], height + 1)
                                                self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
                                        if split:
                                            code = page.locator('.code-slot pre')
                                            self.assertTrue(code.evaluate("el => el.scrollHeight > el.clientHeight"))
                                            page.get_by_role("button", name="Close code").click()
                                            page.wait_for_function("document.querySelector('.shell-panels').dataset.split === 'false'")
                                finally:
                                    context.close()


if __name__ == "__main__":
    unittest.main()
