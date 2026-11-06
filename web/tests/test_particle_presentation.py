"""Particle presentation check against the running web app (requires Chrome).

Run Vite on port 5199, then:
  uv run --no-project --with playwright python web/tests/test_particle_presentation.py
Sends a public scene (a `headline` and a `code` object with a line focus) through a fake
WebSocket and reads the particle canvas pixels: the words must be assembled in the voice
stage, the focused code lines must be outlined, and both must let go when the scene ends.
A second test sends a scene with a 3D `shape` (torus, cone, cube) and a headline: the shape wins
and is assembled as a solid with two colours (front and sides), the headline returns when the
shape is hidden, and under reduced motion the same pose draws the same picture again.
Screenshots go to .impeccable/review/particle-presentation/ (gitignored). No Socra server,
agent, microphone, or stored user data is used.
"""

import base64
import io
import os
import unittest
import wave
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE_URL = os.environ.get("SOCRA_TEST_URL", "http://localhost:5199")
SHOTS = Path(__file__).resolve().parents[2] / ".impeccable" / "review" / "particle-presentation"
SIZES = ((1440, 900), (360, 640))
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
HEADLINE = "Hash tables"

# Reads the particle canvases: the voice stage (headline, sphere) from the background canvas, and
# a ring around the focused lines from the front canvas that sits above the panels. Lit pixel
# counts for a CSS box, for the ring, and the horizontal spread of the lit pixels in the stage
# (5th..95th percentile as a share of its width).
PIXELS = """
() => {
  const reader = (layer) => {
    const canvas = document.querySelector(`[data-testid="particle-visualizer"] canvas[data-layer="${layer}"]`);
    const scale = canvas.width / innerWidth;
    const data = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
    return (x, y) => {
      const px = Math.round(x * scale), py = Math.round(y * scale);
      return px >= 0 && py >= 0 && px < canvas.width && py < canvas.height && data[(py * canvas.width + px) * 4 + 3] > 40;
    };
  };
  const lit = reader('back'), litFront = reader('front');
  const stageBox = document.querySelector('.voice-stage').getBoundingClientRect();
  const xs = [], rows = new Set();
  let stage = 0;
  for (let y = Math.floor(stageBox.top); y < stageBox.bottom; y++) {
    for (let x = Math.floor(stageBox.left); x < stageBox.right; x++) {
      if (lit(x, y)) { stage++; xs.push(x); rows.add(y); }
    }
  }
  xs.sort((a, b) => a - b);
  const spread = xs.length ? (xs[Math.floor(xs.length * 0.95)] - xs[Math.floor(xs.length * 0.05)]) / stageBox.width : 0;
  const bins = new Array(12).fill(0);
  for (const x of xs) bins[Math.min(11, Math.floor(((x - stageBox.left) / stageBox.width) * 12))]++;
  let ring = null;
  const focused = [...document.querySelectorAll('pre[data-scene-object="src"] [data-focused="true"]')];
  if (focused.length) {
    const rects = focused.map((el) => el.getBoundingClientRect());
    const box = { l: Math.min(...rects.map((r) => r.left)), t: Math.min(...rects.map((r) => r.top)),
      r: Math.max(...rects.map((r) => r.right)), b: Math.max(...rects.map((r) => r.bottom)) };
    // Is the front canvas really above the panels? It must be fixed with a positive z-index, and the
    // nearest stacking context around it must also contain the code pane (else it would be trapped
    // in a context that an opaque panel outside it paints over).
    const front = document.querySelector('canvas[data-layer="front"]');
    const fcs = getComputedStyle(front);
    let covered = fcs.position !== 'fixed' || !(parseInt(fcs.zIndex, 10) > 0) ? 'canvas ' + fcs.position + ' z=' + fcs.zIndex : '';
    for (let n = front.parentElement; n && n !== document.documentElement; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if ((cs.position !== 'static' && cs.zIndex !== 'auto') || cs.transform !== 'none' || cs.filter !== 'none' ||
          parseFloat(cs.opacity) < 1 || cs.isolation === 'isolate') {
        if (n.contains(focused[0])) break;
        covered = `${n.tagName}.${n.className} pos=${cs.position} z=${cs.zIndex} tf=${cs.transform} f=${cs.filter} o=${cs.opacity} iso=${cs.isolation}`; break;
      }
    }
    const m = 9;
    let border = 0, inner = 0;
    for (let y = Math.floor(box.t - m); y <= box.b + m; y++) {
      for (let x = Math.floor(box.l - m); x <= box.r + m; x++) {
        if (!litFront(x, y)) continue;
        const outside = x < box.l - m || x > box.r + m || y < box.t - m || y > box.b + m;
        const core = x > box.l + m && x < box.r - m && y > box.t + m && y < box.b - m;
        if (outside) continue;
        if (core) inner++; else border++;
      }
    }
    ring = { border, inner, covered };
  }
  return {
    stage, spread, bins, ring, rows: rows.size, stageBox: { w: stageBox.width, h: stageBox.height },
    figures: document.querySelector('[data-testid="particle-visualizer"]').dataset.figures,
  };
}
"""


# The voice stage's lit pixels on the background canvas: how many, the box they span (2nd..98th
# percentile, as a share of the stage's shorter side), lit pixels per cell of a coarse grid (12 x 12) to compare pictures,
# and the hues (degrees) of the lit pixels in 10-degree bins, so two palette colours show as two peaks.
SHAPE_PIXELS = """
() => {
  const canvas = document.querySelector('[data-testid="particle-visualizer"] canvas[data-layer="back"]');
  const scale = canvas.width / innerWidth;
  const data = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
  const box = document.querySelector('.voice-stage').getBoundingClientRect();
  const xs = [], ys = [], hues = new Array(36).fill(0), mask = new Array(12 * 12).fill(0);
  for (let y = Math.floor(box.top); y < box.bottom; y++) {
    for (let x = Math.floor(box.left); x < box.right; x++) {
      const px = Math.round(x * scale), py = Math.round(y * scale);
      if (px < 0 || py < 0 || px >= canvas.width || py >= canvas.height) continue;
      const i = (py * canvas.width + px) * 4;
      if (data[i + 3] <= 40) continue;
      xs.push(x); ys.push(y);
      const cx = Math.min(11, Math.floor(((x - box.left) / box.width) * 12)), cy = Math.min(11, Math.floor(((y - box.top) / box.height) * 12));
      mask[cy * 12 + cx]++;
      const r = data[i], g = data[i + 1], b = data[i + 2], hi = Math.max(r, g, b), lo = Math.min(r, g, b);
      if (hi - lo < 20) continue;
      let h = hi === r ? ((g - b) / (hi - lo)) % 6 : hi === g ? (b - r) / (hi - lo) + 2 : (r - g) / (hi - lo) + 4;
      h = (h * 60 + 360) % 360;
      hues[Math.floor(h / 10)]++;
    }
  }
  const pct = (list, q) => { list.sort((a, b) => a - b); return list.length ? list[Math.floor((list.length - 1) * q)] : 0; };
  return {
    lit: xs.length,
    w: (pct(xs, 0.98) - pct(xs, 0.02)) / Math.min(box.width, box.height), h: (pct(ys, 0.98) - pct(ys, 0.02)) / Math.min(box.width, box.height),
    side: Math.min(box.width, box.height), stage: { w: box.width, h: box.height }, hues, mask,
    figures: document.querySelector('[data-testid="particle-visualizer"]').dataset.figures,
  };
}
"""


def silent_wav(seconds=30):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(1)
        out.setframerate(8000)
        out.writeframes(b"\x80" * 8000 * seconds)
    return base64.b64encode(buffer.getvalue()).decode()


SCENE = {
    "type": "walkthrough",
    "title": "Hash tables",
    "objects": [
        {"id": "h", "primitive": "headline", "params": {"text": HEADLINE}, "hidden": False},
        {"id": "src", "primitive": "code", "params": {"code": CODE, "language": "python"}, "hidden": False},
    ],
    "total": 2,
}
STEP = {
    "index": 1,
    "total": 2,
    "id": "s1",
    "say": "A hash table maps a key to a slot.",
    "state": {"h": {"visible": True, "text": HEADLINE}, "src": {"visible": True, "lines": [2, 3]}},
}


SHAPE_HEADLINE = "Torus"
SHAPE_OBJECTS = [
    {"id": "h", "primitive": "headline", "params": {"text": SHAPE_HEADLINE}, "hidden": False},
    {"id": "body", "primitive": "shape", "params": {"shape": "torus"}, "hidden": False},
]
SHAPE_SCENE = {"type": "walkthrough", "title": "Solids", "objects": SHAPE_OBJECTS, "total": 5}


def shape_step(seq, say, shape=None, visible=True, **pose):
    body = {"visible": visible, "shape": shape or "torus", "wireframe": False, "rx": 0.0, "ry": 0.0, "rz": 0.0, **pose}
    return {
        "index": seq,
        "total": 5,
        "id": f"s{seq}",
        "say": say,
        "seq": seq,
        "state": {"h": {"visible": True, "text": SHAPE_HEADLINE}, "body": body},
    }


def hue_peaks(hues):
    """The two strongest hue bins at least 20 degrees apart, as shares of all hued pixels."""
    total = sum(hues) or 1
    order = sorted(range(len(hues)), key=lambda i: -hues[i])
    first = order[0]
    second = next((i for i in order[1:] if min((i - first) % 36, (first - i) % 36) >= 2), first)
    return hues[first] / total, hues[second] / total


class ParticlePresentationTest(unittest.TestCase):
    def settle(self, page, ms=3000):
        page.evaluate("async () => { await document.fonts.ready; }")
        page.wait_for_timeout(ms)

    def test_particles_present_headline_and_code_focus(self):
        SHOTS.mkdir(parents=True, exist_ok=True)
        wav = silent_wav()
        with sync_playwright() as playwright:
            with playwright.chromium.launch(
                channel="chrome", args=["--autoplay-policy=no-user-gesture-required"]
            ) as browser:
                for mode in ("agent", "exam"):
                    for theme in ("dark", "light"):
                        for width, height in SIZES:
                            with self.subTest(mode=mode, theme=theme, size=(width, height)):
                                context = browser.new_context(viewport={"width": width, "height": height})
                                context.add_init_script(SOCKET + f"localStorage.setItem('socra_theme', '{theme}');")
                                page = context.new_page()
                                tag = f"{mode}-{theme}-{width}x{height}"
                                try:
                                    self.run_case(page, mode, wav, tag)
                                finally:
                                    context.close()

    def prepare(self, page, mode):
        page.goto(f"{BASE_URL}/?mode={mode}")
        page.get_by_test_id("particle-visualizer").wait_for()
        page.wait_for_function("window.testSockets.some(s => s.onmessage)")
        page.evaluate(
            """mode => {
              const ws = window.testSockets.find(s => s.onmessage);
              if (mode === 'agent') ws.receive({type: 'agent_started', backend: 'claude-code', model: 'sonnet', cwd: 'C:/test'});
              else ws.receive({type: 'question', index: 1, total: 1, text: 'Explain hash tables.'});
              ws.receive({type: 'state', state: 'speaking'});
            }""",
            mode,
        )

    def run_case(self, page, mode, wav, tag):
        self.prepare(page, mode)
        # S4: without a scene the formation is the voice formation (no figures).
        self.settle(page)
        before = page.evaluate(PIXELS)
        self.assertEqual(before["figures"], "", tag)
        self.assertGreater(before["stage"], 200, f"{tag}: voice formation is lit {before}")
        page.screenshot(path=str(SHOTS / f"{tag}-1-no-scene.png"))

        # S1/S3: the scene arrives; the step shows when its audio starts.
        page.evaluate(
            """([scene, step, wav]) => {
              const ws = window.testSockets.find(s => s.onmessage);
              ws.receive(scene);
              ws.receive({type: 'tts_audio', format: 'wav', data: wav, step: {...step, seq: 1}});
              ws.receive({type: 'state', state: 'speaking'});
            }""",
            [SCENE, STEP, wav],
        )
        page.wait_for_function(
            "document.querySelector('[data-testid=\"particle-visualizer\"]').dataset.figures.includes('headline')",
            timeout=10000,
        )
        self.settle(page)
        during = page.evaluate(PIXELS)
        page.screenshot(path=str(SHOTS / f"{tag}-2-scene.png"))
        print(f"{tag} before={before['stage']}/{before['spread']:.2f} during={during['stage']}/{during['spread']:.2f} "
              f"bins={during['bins']} ring={during['ring']}")
        self.assertIn(f"headline:h:{HEADLINE}", during["figures"], tag)
        self.assertIn("focus:src:2-3", during["figures"], tag)
        # The words fill most of the stage width and several rows, unlike the sphere.
        self.assertGreater(during["spread"], 0.5, f"{tag}: headline is not spread like words {during}")
        self.assertGreaterEqual(sum(1 for b in during["bins"] if b > 15), 8, f"{tag}: lit columns {during['bins']}")
        self.assertGreater(during["spread"], before["spread"] + 0.15, f"{tag}: no wider than the voice formation")
        # The focus is outlined: lit pixels on the border of the focused lines' rectangle, and
        # the front canvas that carries them sits above the panels.
        with self.subTest(part="outline"):
            self.assertIsNotNone(during["ring"], f"{tag}: no focused line")
            self.assertGreater(during["ring"]["border"], 25, f"{tag}: outline is missing {during['ring']}")
            self.assertEqual(during["ring"]["covered"], "", f"{tag}: outline canvas is not above the panels")

        # The scene ends: the figures let go and the stage goes back to the voice formation.
        page.evaluate(
            """() => window.testSockets.find(s => s.onmessage)
              .receive({type: 'walkthrough_status', status: 'ended', reason: 'completed'})"""
        )
        self.settle(page)
        after = page.evaluate(PIXELS)
        page.screenshot(path=str(SHOTS / f"{tag}-3-ended.png"))
        self.assertEqual(after["figures"], "", tag)
        self.assertLess(after["spread"], during["spread"] - 0.1, f"{tag}: still spread like words {after}")

    def show(self, page, step, wav, expect, wait_ms=3000):
        page.evaluate(
            """([step, wav]) => window.testSockets.find(s => s.onmessage)
              .receive({type: 'tts_audio', format: 'wav', data: wav, step})""",
            [step, wav],
        )
        page.wait_for_function(
            f"document.querySelector('[data-testid=\"particle-visualizer\"]').dataset.figures.includes('{expect}')",
            timeout=10000,
        )
        self.settle(page, wait_ms)
        return page.evaluate(SHAPE_PIXELS)

    def test_particles_assemble_a_shape_and_it_wins_over_a_headline(self):
        SHOTS.mkdir(parents=True, exist_ok=True)
        wav = silent_wav()
        with sync_playwright() as playwright:
            with playwright.chromium.launch(
                channel="chrome", args=["--autoplay-policy=no-user-gesture-required"]
            ) as browser:
                for mode in ("agent", "exam"):
                    for theme in ("dark", "light"):
                        for width, height in SIZES:
                            with self.subTest(mode=mode, theme=theme, size=(width, height)):
                                context = browser.new_context(viewport={"width": width, "height": height})
                                context.add_init_script(SOCKET + f"localStorage.setItem('socra_theme', '{theme}');")
                                page = context.new_page()
                                try:
                                    self.run_shape_case(page, mode, wav, f"shape-{mode}-{theme}-{width}x{height}")
                                finally:
                                    context.close()

    def run_shape_case(self, page, mode, wav, tag):
        self.prepare(page, mode)
        self.settle(page)
        page.evaluate("scene => window.testSockets.find(s => s.onmessage).receive(scene)", SHAPE_SCENE)

        # Shape and headline are both visible: the shape takes the particles, the headline is not drawn.
        torus = self.show(page, shape_step(1, "A torus is a ring."), wav, "shape:body:torus")
        page.screenshot(path=str(SHOTS / f"{tag}-1-torus.png"))
        print(f"{tag} torus lit={torus['lit']} w={torus['w']:.2f} h={torus['h']:.2f} peaks={hue_peaks(torus['hues'])}")
        self.assertIn("shape:body:torus:solid", torus["figures"], tag)
        self.assertNotIn("headline", torus["figures"], f"{tag}: the headline is drawn under the shape")
        # A solid in the stage: lit, spread over a good part of it, and in two colours (front and
        # sides) rather than a mix of hues.
        self.assertGreater(torus["lit"], 400, f"{tag}: torus is barely lit {torus}")
        self.assertGreater(torus["w"], 0.3, f"{tag}: torus spans {torus['w']:.2f} of the stage's shorter side")
        self.assertGreater(torus["h"], 0.2, f"{tag}: torus spans {torus['h']:.2f} of the stage's shorter side")
        main, other = hue_peaks(torus["hues"])
        self.assertGreater(min(main, other), 0.12, f"{tag}: sides and front are not two colours {torus['hues']}")

        cone = self.show(page, shape_step(2, "A cone narrows to a point.", shape="cone"), wav, "shape:body:cone")
        page.screenshot(path=str(SHOTS / f"{tag}-2-cone.png"))
        print(f"{tag} cone lit={cone['lit']} w={cone['w']:.2f} h={cone['h']:.2f} peaks={hue_peaks(cone['hues'])}")
        self.assertNotIn("headline", cone["figures"], tag)
        self.assertGreater(cone["lit"], 400, f"{tag}: cone is barely lit {cone}")
        self.assertGreater(cone["h"], 0.3, f"{tag}: cone spans {cone['h']:.2f} of the stage's shorter side")
        self.assertNotEqual(
            [c >= 25 for c in cone["mask"]], [c >= 25 for c in torus["mask"]], f"{tag}: cone and torus draw the same picture"
        )

        cube = self.show(page, shape_step(3, "A cube has six faces.", shape="cube", rx=0.1, ry=0.15), wav, "shape:body:cube")
        page.screenshot(path=str(SHOTS / f"{tag}-3-cube.png"))
        self.assertGreater(cube["lit"], 400, f"{tag}: cube is barely lit {cube}")

        # Hiding the shape releases the particles; the headline takes the stage again.
        head = self.show(page, shape_step(4, "Now the word.", visible=False), wav, "headline:h")
        page.screenshot(path=str(SHOTS / f"{tag}-4-shape-hidden.png"))
        self.assertNotIn("shape:", head["figures"], tag)
        self.assertIn(f"headline:h:{SHAPE_HEADLINE}", head["figures"], tag)

    def test_same_pose_draws_the_same_picture_when_a_step_is_shown_again(self):
        wav = silent_wav()
        with sync_playwright() as playwright:
            with playwright.chromium.launch(
                channel="chrome", args=["--autoplay-policy=no-user-gesture-required"]
            ) as browser:
                # Reduced motion holds the idle turn still, so the pose comes from the scene state alone.
                context = browser.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
                context.add_init_script(SOCKET + "localStorage.setItem('socra_theme', 'dark');")
                page = context.new_page()
                try:
                    self.prepare(page, "agent")
                    self.settle(page)
                    page.evaluate("scene => window.testSockets.find(s => s.onmessage).receive(scene)", SHAPE_SCENE)
                    first = self.show(page, shape_step(1, "One.", shape="cube", rx=0.1, ry=0.1), wav, "shape:body:cube")
                    turned = self.show(page, shape_step(2, "Two.", shape="cube", rx=0.3, ry=0.45), wav, "shape:body:cube")
                    again = self.show(page, shape_step(3, "Back.", shape="cube", rx=0.1, ry=0.1), wav, "shape:body:cube")
                    later = page.evaluate(SHAPE_PIXELS)
                finally:
                    context.close()

        def cells(shot):
            return {i for i, count in enumerate(shot["mask"]) if count >= 25}

        def same(a, b):
            """Share of the cells lit enough in either picture that are lit in both."""
            return len(cells(a) & cells(b)) / max(1, len(cells(a) | cells(b)))

        print(f"pose again={same(first, again):.2f} turned={same(first, turned):.2f} self={same(again, later):.2f} cells={len(cells(first))}")
        self.assertGreater(same(first, again), 0.75, "going back to the earlier pose does not restore its picture")
        self.assertLess(same(first, turned), same(first, again) - 0.08, "rotate did not change the picture")


if __name__ == "__main__":
    unittest.main()
