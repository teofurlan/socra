"""Particle presentation check against the running web app (requires Chrome).

Run Vite on port 5199, then:
  uv run --no-project --with playwright python web/tests/test_particle_presentation.py
Sends a public scene (a `headline` and a `code` object with a line focus) through a fake
WebSocket and reads the particle canvas pixels: the words must be assembled in the voice
stage, the focused code lines must be outlined, and both must let go when the scene ends.
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

    def run_case(self, page, mode, wav, tag):
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


if __name__ == "__main__":
    unittest.main()
