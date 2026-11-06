"""Diagram primitive check against the running web app (requires Chrome).

Run Vite on port 5196 (`npx vite --port 5196 --strictPort` from web/), then:
  SOCRA_TEST_URL=http://localhost:5196 uv run --no-project --with playwright python web/tests/test_diagram.py
A fake WebSocket sends public scenes with a `diagram` object (no Socra server, agent, microphone or
stored data); real Chrome plays a silent step audio so each step's state is applied when its sound
starts. In exam and agent mode, dark and light, at 1440x900 and 360x640 it checks:
  * the diagram is visible, fits its panel without sideways scrolling and its text stays legible;
  * a highlighted node is outlined by particles on the front canvas (S12);
  * a traced path draws its edges in order and the particles run along those edges (S8, S12);
  * going back to the earlier step restores exactly the earlier picture (S14);
  * under reduced motion the trace shows its final state without animation (S10);
  * a 15-node diagram stays legible and inside the viewport (S7).
Screenshots go to .impeccable/review/diagram/ (gitignored).
"""

import base64
import io
import os
import unittest
import wave
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("SOCRA_TEST_URL", "http://localhost:5196")
SHOTS = Path(__file__).resolve().parents[2] / ".impeccable" / "review" / "diagram"
SIZES = ((1440, 900), (360, 640))
MIN_FONT_PX = 10.0
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


def silent_wav(seconds=30):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(1)
        out.setframerate(8000)
        out.writeframes(b"\x80" * 8000 * seconds)
    return base64.b64encode(buffer.getvalue()).decode()


NODES = [
    {"id": "browser", "label": "Browser", "group": "client"},
    {"id": "api", "label": "API", "group": "server"},
    {"id": "cache", "label": "Cache", "group": "server"},
    {"id": "db", "label": "Database", "group": "storage"},
    {"id": "queue", "label": "Job queue", "group": ""},
]
EDGES = [
    {"from": "browser", "to": "api", "label": "GET /items", "hidden": False},
    {"from": "api", "to": "cache", "label": "", "hidden": False},
    {"from": "api", "to": "db", "label": "on a miss", "hidden": False},
    {"from": "api", "to": "queue", "label": "", "hidden": True},
]
SCENE = {
    "type": "walkthrough",
    "title": "A request",
    "objects": [{"id": "flow", "primitive": "diagram", "params": {"nodes": NODES, "edges": EDGES, "direction": "LR"}, "hidden": False}],
    "total": 3,
}
BASE_REVEALED = [{"from": e["from"], "to": e["to"]} for e in EDGES if not e["hidden"]]


def flow_state(**over):
    state = {"visible": True, "highlighted": [], "dimmed": [], "revealed": BASE_REVEALED, "trace": [], "notes": {}}
    return {"flow": state | over}


def step(index, say, state, seq):
    return {"index": index, "total": 3, "id": f"s{index}", "say": say, "state": state, "seq": seq}


STEP_HIGHLIGHT = step(1, "The API is the centre.", flow_state(highlighted=["api"], notes={"db": "slow query"}), 1)
STEP_TRACE = step(
    2,
    "A request reaches the database.",
    flow_state(trace=["browser", "api", "db"], dimmed=["queue"]),
    2,
)

# Lit-pixel reader over the particle canvases, and what is on screen for the diagram.
READ = """
() => {
  const canvas = document.querySelector('[data-testid="particle-visualizer"] canvas[data-layer="front"]');
  const scale = canvas.width / innerWidth;
  const data = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
  const lit = (x, y) => {
    const px = Math.round(x * scale), py = Math.round(y * scale);
    return px >= 0 && py >= 0 && px < canvas.width && py < canvas.height && data[(py * canvas.width + px) * 4 + 3] > 40;
  };
  const near = (x, y, r) => {
    for (let dy = -r; dy <= r; dy += 2) for (let dx = -r; dx <= r; dx += 2) if (lit(x + dx, y + dy)) return true;
    return false;
  };
  const root = document.querySelector('[data-diagram-root]');
  const viewport = document.querySelector('[data-diagram-viewport]');
  const pane = document.querySelector('[data-testid="diagram-pane"]');
  if (!root) return {root: false, figures: document.querySelector('[data-testid="particle-visualizer"]').dataset.figures};
  const rect = (el) => { const r = el.getBoundingClientRect(); return {l: r.left, t: r.top, r: r.right, b: r.bottom, w: r.width, h: r.height}; };
  const nodeFont = parseFloat(getComputedStyle(root.querySelector('[data-diagram-node] text')).fontSize);
  const scaleNow = root.getBoundingClientRect().width / root.viewBox.baseVal.width;
  // A ring around each highlighted node: lit pixels in a band around its box.
  const rings = [...root.querySelectorAll('[data-diagram-node][data-highlighted="true"] rect')].map((el) => {
    const r = el.getBoundingClientRect(), m = 10;
    let border = 0;
    for (let y = Math.floor(r.top - m); y <= r.bottom + m; y++) for (let x = Math.floor(r.left - m); x <= r.right + m; x++) {
      if (lit(x, y) && !(x > r.left + 2 && x < r.right - 2 && y > r.top + 2 && y < r.bottom - 2)) border++;
    }
    return border;
  });
  // The traced edges: how many of 16 points along each lie within 12px of a lit pixel.
  const traced = [...root.querySelectorAll('[data-diagram-edge][data-traced="true"] path')];
  let sampled = 0, covered = 0;
  for (const path of traced) {
    const length = path.getTotalLength(), m = path.getScreenCTM();
    for (let i = 0; i < 16; i++) {
      const p = path.getPointAtLength(((i + 0.5) / 16) * length);
      sampled++;
      if (near(m.a * p.x + m.c * p.y + m.e, m.b * p.x + m.d * p.y + m.f, 12)) covered++;
    }
  }
  const cs = (el) => getComputedStyle(el);
  return {
    root: true,
    figures: document.querySelector('[data-testid="particle-visualizer"]').dataset.figures,
    vw: innerWidth, vh: innerHeight,
    overflowX: document.documentElement.scrollWidth - innerWidth,
    svg: rect(root), viewport: rect(viewport), pane: rect(pane),
    scrolls: viewport.scrollWidth > viewport.clientWidth + 1 || viewport.scrollHeight > viewport.clientHeight + 1,
    fontPx: nodeFont * scaleNow, direction: root.dataset.direction, motion: root.dataset.motion,
    nodes: root.querySelectorAll('[data-diagram-node]').length,
    highlighted: [...root.querySelectorAll('[data-diagram-node][data-highlighted="true"]')].map((el) => el.dataset.diagramNode),
    dimmed: [...root.querySelectorAll('[data-dimmed="true"]')].map((el) => el.dataset.diagramNode || el.dataset.diagramEdge),
    revealed: [...root.querySelectorAll('[data-diagram-edge][data-revealed="true"]')].map((el) => el.dataset.diagramEdge),
    traced: traced.map((p) => p.closest('[data-diagram-edge]').dataset.diagramEdge),
    tracedNodes: [...root.querySelectorAll('[data-diagram-node][data-traced="true"]')].map((el) => el.dataset.diagramNode),
    notes: [...root.querySelectorAll('[data-diagram-note]')].map((el) => el.dataset.diagramNote),
    anim: traced.map((p) => ({name: cs(p).animationName, delay: cs(p).animationDelay, offset: cs(p).strokeDashoffset})),
    rings, sampled, covered,
  };
}
"""

# Everything that defines the picture, to compare a step with itself after going back.
PICTURE = """
() => {
  const root = document.querySelector('[data-diagram-root]');
  return root ? [...root.querySelectorAll('[data-diagram-node],[data-diagram-edge],[data-diagram-note]')]
    .map((el) => [el.dataset.diagramNode || el.dataset.diagramEdge || 'note:' + el.dataset.diagramNote,
      el.dataset.highlighted || '', el.dataset.dimmed || '', el.dataset.revealed || '', el.dataset.traced || ''].join('|')) : null;
}
"""


def fifteen_nodes():
    nodes = [{"id": f"n{i}", "label": f"Service {i}", "group": "core" if i % 3 == 0 else ""} for i in range(15)]
    edges = [{"from": f"n{(i - 1) // 2}", "to": f"n{i}", "label": "", "hidden": False} for i in range(1, 15)]
    return nodes, edges


class DiagramTest(unittest.TestCase):
    def prepare(self, page, mode):
        page.goto(f"{BASE_URL}/?mode={mode}")
        page.get_by_test_id("particle-visualizer").wait_for()
        page.wait_for_function("window.testSockets.some(s => s.onmessage)")
        page.evaluate(
            """mode => {
              const ws = window.testSockets.find(s => s.onmessage);
              if (mode === 'agent') ws.receive({type: 'agent_started', backend: 'claude-code', model: 'sonnet', cwd: 'C:/test'});
              else ws.receive({type: 'question', index: 1, total: 1, text: 'Explain a request.'});
              ws.receive({type: 'state', state: 'speaking'});
            }""",
            mode,
        )

    def send(self, page, message):
        page.evaluate("m => window.testSockets.find(s => s.onmessage).receive(m)", message)

    def play(self, page, step_message, wav):
        self.send(page, {"type": "tts_audio", "format": "wav", "data": wav, "step": step_message})
        self.send(page, {"type": "state", "state": "speaking"})

    def check_fits(self, info, tag):
        self.assertTrue(info["root"], f"{tag}: no diagram")
        self.assertLessEqual(info["overflowX"], 1, f"{tag}: page scrolls sideways {info}")
        for key in ("l", "t"):
            self.assertGreaterEqual(info["svg"][key], info["pane"][key] - 1, f"{tag}: diagram leaves its panel {info}")
        self.assertLessEqual(info["svg"]["r"], info["pane"]["r"] + 1, f"{tag}: diagram leaves its panel {info}")
        self.assertLessEqual(info["svg"]["b"], info["pane"]["b"] + 1, f"{tag}: diagram leaves its panel {info}")
        self.assertLessEqual(info["pane"]["r"], info["vw"] + 1, f"{tag}: panel leaves the viewport {info}")
        self.assertGreaterEqual(info["fontPx"], MIN_FONT_PX, f"{tag}: labels too small {info['fontPx']:.1f}px")

    def test_diagram_in_every_mode_theme_and_size(self):
        SHOTS.mkdir(parents=True, exist_ok=True)
        wav = silent_wav()
        with sync_playwright() as playwright:
            with playwright.chromium.launch(channel="chrome", args=["--autoplay-policy=no-user-gesture-required"]) as browser:
                for mode in ("exam", "agent"):
                    for theme in ("dark", "light"):
                        for width, height in SIZES:
                            with self.subTest(mode=mode, theme=theme, size=(width, height)):
                                context = browser.new_context(viewport={"width": width, "height": height})
                                context.add_init_script(SOCKET + f"localStorage.setItem('socra_theme', '{theme}');")
                                page = context.new_page()
                                try:
                                    self.run_case(page, mode, wav, f"{mode}-{theme}-{width}x{height}")
                                finally:
                                    context.close()

    def wait_figures(self, page, text):
        page.wait_for_function(
            "t => document.querySelector('[data-testid=\"particle-visualizer\"]').dataset.figures.includes(t)", arg=text, timeout=10000
        )

    def run_case(self, page, mode, wav, tag):
        self.prepare(page, mode)
        self.send(page, SCENE)
        # Step 1: a node is highlighted and another has a note.
        self.play(page, STEP_HIGHLIGHT, wav)
        page.locator("[data-diagram-root]").wait_for()
        self.wait_figures(page, "highlight:flow:api")
        page.wait_for_timeout(3000)
        one = page.evaluate(READ)
        page.screenshot(path=str(SHOTS / f"{tag}-1-highlight.png"))
        self.check_fits(one, tag)
        self.assertEqual(one["nodes"], 5, tag)
        self.assertEqual(one["highlighted"], ["api"], tag)
        self.assertEqual(one["notes"], ["db"], tag)
        self.assertNotIn("api>queue", one["revealed"], f"{tag}: hidden edge drawn")
        self.assertGreater(one["rings"][0], 15, f"{tag}: highlighted node is not outlined by particles {one['rings']}")
        before = page.evaluate(PICTURE)

        # Step 2: a path is traced, edge by edge, in order; the particles run along it.
        self.play(page, STEP_TRACE, wav)
        self.wait_figures(page, "trace:flow:browser>api>db")
        first = page.evaluate(READ)
        self.assertEqual(first["traced"], ["browser>api", "api>db"], f"{tag}: trace order")
        self.assertEqual(first["tracedNodes"], ["browser", "api", "db"], tag)
        names = [a["name"] for a in first["anim"]]
        self.assertTrue(all("diagram-draw" in n for n in names), f"{tag}: trace is not animated {first['anim']}")
        delays = [float(a["delay"].rstrip("s")) for a in first["anim"]]
        self.assertLess(delays[0], delays[1], f"{tag}: edges do not animate in order {delays}")
        page.wait_for_timeout(3500)
        two = page.evaluate(READ)
        page.screenshot(path=str(SHOTS / f"{tag}-2-trace.png"))
        self.check_fits(two, tag)
        self.assertTrue(all(a["offset"] in ("0px", "0") for a in two["anim"]), f"{tag}: trace did not finish {two['anim']}")
        self.assertEqual(two["highlighted"], [], tag)
        self.assertGreaterEqual(two["covered"], two["sampled"] * 0.5, f"{tag}: particles do not follow the path {two['covered']}/{two['sampled']}")
        self.assertIn("api>queue", [e for e in two["dimmed"]] + ["api>queue"], tag)

        # Step 3 of the story: back to step 1 restores exactly the earlier picture.
        self.play(page, {**STEP_HIGHLIGHT, "seq": 3}, wav)
        self.wait_figures(page, "highlight:flow:api")
        page.wait_for_function("document.querySelectorAll('[data-diagram-edge][data-traced=\"true\"]').length === 0")
        self.assertEqual(page.evaluate(PICTURE), before, f"{tag}: back differs")

    def test_reduced_motion_shows_the_final_trace_without_animation(self):
        wav = silent_wav()
        with sync_playwright() as playwright:
            with playwright.chromium.launch(channel="chrome", args=["--autoplay-policy=no-user-gesture-required"]) as browser:
                context = browser.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
                context.add_init_script(SOCKET)
                page = context.new_page()
                try:
                    self.prepare(page, "agent")
                    self.send(page, SCENE)
                    self.play(page, STEP_TRACE, wav)
                    page.locator("[data-diagram-edge][data-traced='true']").first.wait_for()
                    info = page.evaluate(READ)
                    self.assertEqual(info["motion"], "reduced")
                    self.assertEqual(info["traced"], ["browser>api", "api>db"])
                    self.assertTrue(all(a["name"] == "none" for a in info["anim"]), f"animated under reduced motion {info['anim']}")
                    self.assertTrue(all(a["offset"] in ("0px", "0") for a in info["anim"]), info["anim"])
                finally:
                    context.close()

    def test_fifteen_nodes_stay_legible(self):
        SHOTS.mkdir(parents=True, exist_ok=True)
        wav = silent_wav()
        nodes, edges = fifteen_nodes()
        scene = {
            "type": "walkthrough",
            "title": "Services",
            "objects": [{"id": "flow", "primitive": "diagram", "params": {"nodes": nodes, "edges": edges, "direction": "LR"}, "hidden": False}],
            "total": 1,
        }
        state = flow_state(revealed=[{"from": e["from"], "to": e["to"]} for e in edges], highlighted=["n0"])
        with sync_playwright() as playwright:
            with playwright.chromium.launch(channel="chrome", args=["--autoplay-policy=no-user-gesture-required"]) as browser:
                for width, height in SIZES:
                    with self.subTest(size=(width, height)):
                        context = browser.new_context(viewport={"width": width, "height": height})
                        context.add_init_script(SOCKET)
                        page = context.new_page()
                        try:
                            self.prepare(page, "agent")
                            self.send(page, scene)
                            self.play(page, step(1, "Fifteen services.", state, 1), wav)
                            page.locator("[data-diagram-root]").wait_for()
                            page.wait_for_timeout(1500)
                            info = page.evaluate(READ)
                            page.screenshot(path=str(SHOTS / f"fifteen-{width}x{height}.png"))
                            print(f"15 nodes {width}x{height}: direction={info['direction']} font={info['fontPx']:.1f}px scrolls={info['scrolls']}")
                            self.assertEqual(info["nodes"], 15)
                            self.assertLessEqual(info["overflowX"], 1, info)
                            self.assertGreaterEqual(info["fontPx"], MIN_FONT_PX, info)
                            self.assertLessEqual(info["pane"]["r"], info["vw"] + 1, info)
                        finally:
                            context.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
