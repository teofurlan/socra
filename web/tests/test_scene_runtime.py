"""Scene runtime check against the running web app (requires Chrome).

Run Vite on port 5197 (`npx vite --port 5197 --strictPort` from web/), then:
  SOCRA_TEST_URL=http://localhost:5197 uv run --no-project --with playwright python web/tests/test_scene_runtime.py
A fake WebSocket sends public scenes (no Socra server, agent, microphone or stored data). Real
Chrome decodes and plays the step audio (a short silent WAV), so a step's cue is applied when
its sound starts, as in a real session. It checks, in exam and agent mode, at 1440x900 and 360x640:
  * the code walkthrough shows its code and moves its line focus with each step (S4, S7);
  * going back to a step restores exactly the same focus and visible state (S8);
  * an unknown primitive shows the step's text and the controls keep working (S5);
  * the content panel and controls fit the viewport without sideways scrolling (S10);
  * first visual and cue drift, read from window.__socraSceneMetrics (S6, S9).
The measurements are printed as a markdown block (METRICS_RUNS scenes, default 10).
"""

import base64
import io
import os
import statistics
import unittest
import wave

from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("SOCRA_TEST_URL", "http://localhost:5197")
RUNS = int(os.environ.get("METRICS_RUNS", "10"))
SIZES = ((1440, 900), (360, 640))
FIRST_VISUAL_BUDGET_MS = 1500
DRIFT_BUDGET_MS = 300
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
  send(data) { (window.sent = window.sent || []).push(data); }
  close() {}
  receive(data) { this.onmessage?.({data: JSON.stringify(data)}); }
};
"""
CODE = "\n".join(
    [
        "table = {}",
        "def put(key, value):",
        "    slot = hash(key) % 8",
        "    table.setdefault(slot, []).append((key, value))",
        "def get(key):",
        "    for k, v in table.get(hash(key) % 8, []):",
        "        if k == key:",
        "            return v",
    ]
)
SCENE = {
    "type": "walkthrough",
    "title": "Hash tables",
    "objects": [
        {"id": "h", "primitive": "headline", "params": {"text": "Hash tables"}, "hidden": False},
        {"id": "src", "primitive": "code", "params": {"code": CODE, "language": "python"}, "hidden": False},
    ],
    "total": 3,
}
UNKNOWN_SCENE = {
    "type": "walkthrough",
    "title": "Graph",
    "objects": [{"id": "g", "primitive": "hologram", "params": {}, "hidden": False}],
    "total": 1,
}
FOCUS_JS = """() => ({
  focused: [...document.querySelectorAll('pre[data-scene-object="src"] [data-focused="true"]')].map((el) => el.textContent),
  panels: document.querySelectorAll('[data-testid="code-pane"]').length,
})"""
METRICS_JS = "() => window.__socraSceneMetrics.snapshot()"
LAYOUT_JS = """() => {
  const rect = (el) => el && el.getBoundingClientRect();
  const pane = rect(document.querySelector('[data-testid="code-pane"], [data-testid="scene-fallback"]'));
  const controls = rect(document.querySelector('[data-testid="walkthrough-panel"]'));
  return {
    overflowX: document.documentElement.scrollWidth - innerWidth,
    pane: pane && {l: pane.left, r: pane.right, t: pane.top, b: pane.bottom, w: pane.width, h: pane.height},
    controls: controls && {l: controls.left, r: controls.right, w: controls.width},
    vw: innerWidth, vh: innerHeight,
  };
}"""


def wav_b64(seconds):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(1)
        out.setframerate(8000)
        out.writeframes(b"\x80" * int(8000 * seconds))
    return base64.b64encode(buffer.getvalue()).decode()


def step(index, total, say, lines, seq):
    state = {"h": {"visible": True, "text": "Hash tables"}, "src": {"visible": True, "lines": lines}}
    return {"index": index, "total": total, "id": f"s{index}", "say": say, "state": state, "seq": seq}


STEPS = [
    step(1, 3, "A hash table maps a key to a slot.", [2, 3], 1),
    step(2, 3, "Reading goes the same way.", [5, 8], 2),
    step(3, 3, "The whole thing.", [1, 8], 3),
]
RESULTS = []


def percentile(values, q):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round((len(ordered) - 1) * q)))]


class SceneRuntimeTest(unittest.TestCase):
    def prepare(self, page, mode):
        page.goto(f"{BASE_URL}/?mode={mode}")
        page.wait_for_function("window.testSockets.some(s => s.onmessage)")
        page.evaluate(
            """mode => {
              const ws = window.testSockets.find(s => s.onmessage);
              if (mode === 'agent') ws.receive({type: 'agent_started', backend: 'claude-code', model: 'sonnet', cwd: 'C:/test'});
              else ws.receive({type: 'question', index: 1, total: 1, text: 'Explain hash tables.'});
            }""",
            mode,
        )

    def send(self, page, message):
        page.evaluate("m => window.testSockets.find(s => s.onmessage).receive(m)", message)

    def play(self, page, spoken, wav, wait_drifts):
        self.send(page, {"type": "tts_audio", "format": "wav", "data": wav, "step": spoken})
        page.wait_for_function(f"window.__socraSceneMetrics.snapshot().drifts.length >= {wait_drifts}", timeout=10000)

    def test_scene_runtime(self):
        wav = wav_b64(0.4)
        with sync_playwright() as playwright:
            with playwright.chromium.launch(
                channel="chrome", args=["--autoplay-policy=no-user-gesture-required"]
            ) as browser:
                for mode in ("exam", "agent"):
                    for width, height in SIZES:
                        with self.subTest(mode=mode, size=(width, height)):
                            context = browser.new_context(viewport={"width": width, "height": height})
                            context.add_init_script(SOCKET)
                            page = context.new_page()
                            try:
                                self.run_case(page, mode, wav, f"{mode} {width}x{height}")
                            finally:
                                context.close()

    def run_case(self, page, mode, wav, tag):
        self.prepare(page, mode)
        firsts, drifts = [], []
        for run in range(RUNS):
            self.send(page, SCENE)
            page.get_by_test_id("code-pane").wait_for()
            first = page.evaluate(METRICS_JS)["firstVisualMs"]
            self.assertIsNotNone(first, f"{tag}: no first visual recorded")
            firsts.append(first)
            states = []
            for n, spoken in enumerate(STEPS, start=1):
                self.play(page, spoken, wav, n)
                states.append(page.evaluate(FOCUS_JS))
                if run == 0 and n == 2:
                    page.wait_for_timeout(100)
            self.assertEqual(len(states[0]["focused"]), 2, f"{tag}: step 1 focus {states[0]}")
            self.assertEqual(len(states[1]["focused"]), 4, f"{tag}: step 2 focus {states[1]}")
            self.assertEqual(len(states[2]["focused"]), 8, f"{tag}: step 3 focus {states[2]}")
            # S8: back to step 2 and step 1 restores exactly the same visual state.
            self.play(page, {**STEPS[1], "seq": 4}, wav, 4)
            self.assertEqual(page.evaluate(FOCUS_JS), states[1], f"{tag}: back to step 2 differs")
            self.play(page, {**STEPS[0], "seq": 5}, wav, 5)
            self.assertEqual(page.evaluate(FOCUS_JS), states[0], f"{tag}: back to step 1 differs")
            drifts.extend(d["ms"] for d in page.evaluate(METRICS_JS)["drifts"])
            if run == 0:
                self.check_layout(page, tag)
        RESULTS.append((tag, firsts, drifts))

        # S5: an unknown primitive shows the step's text; the session and its controls carry on.
        self.send(page, UNKNOWN_SCENE)
        step_one = {"index": 1, "total": 1, "id": "s1", "say": "Boxes and arrows.", "state": {"g": {"visible": True}}, "seq": 9}
        self.send(page, {"type": "tts_audio", "format": "wav", "data": wav, "step": step_one})
        page.get_by_test_id("scene-fallback").wait_for()
        self.assertIn("Boxes and arrows.", page.get_by_test_id("scene-fallback").inner_text())
        self.check_layout(page, f"{tag} fallback")
        page.get_by_role("button", name="Pause").click()
        sent = page.evaluate("window.sent || []")
        self.assertTrue(any('"action":"pause"' in m for m in sent), f"{tag}: pause button sent nothing")

    def check_layout(self, page, tag):
        layout = page.evaluate(LAYOUT_JS)
        self.assertLessEqual(layout["overflowX"], 1, f"{tag}: page scrolls sideways {layout}")
        pane = layout["pane"]
        self.assertIsNotNone(pane, f"{tag}: no scene panel")
        self.assertGreater(pane["w"], 100, f"{tag}: panel too narrow {layout}")
        self.assertGreater(pane["h"], 60, f"{tag}: panel too short {layout}")
        self.assertLessEqual(pane["r"], layout["vw"] + 1, f"{tag}: panel leaves the viewport {layout}")
        self.assertLessEqual(layout["controls"]["r"], layout["vw"] + 1, f"{tag}: controls leave the viewport {layout}")


def report():
    print(""); print("| mode / viewport | scenes | first visual p50 / max (ms) | cue drift p50 / max (ms) | cues |")
    print("|---|---|---|---|---|")
    worst_first, worst_drift = 0, 0
    for tag, firsts, drifts in RESULTS:
        worst_first, worst_drift = max(worst_first, max(firsts)), max(worst_drift, max(drifts))
        print(f"| {tag} | {len(firsts)} | {percentile(firsts, .5):.0f} / {max(firsts):.0f} | "
              f"{percentile(drifts, .5):.0f} / {max(drifts):.0f} | {len(drifts)} |")
    print(); print(f"worst first visual {worst_first:.0f} ms (budget {FIRST_VISUAL_BUDGET_MS}), "
          f"worst cue drift {worst_drift:.0f} ms (budget {DRIFT_BUDGET_MS})")
    return worst_first, worst_drift


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2).result
    if RESULTS:
        first, drift = report()
        assert first < FIRST_VISUAL_BUDGET_MS and drift < DRIFT_BUDGET_MS, "scene timing over budget"
    raise SystemExit(0 if result.wasSuccessful() else 1)
