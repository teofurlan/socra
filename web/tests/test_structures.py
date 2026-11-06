"""Structure primitive check against the running web app (requires Chrome).

Run Vite on port 5195 (`npx vite --port 5195 --strictPort` from web/), then:
  SOCRA_TEST_URL=http://localhost:5195 uv run --no-project --with playwright python web/tests/test_structures.py
A fake WebSocket sends public scenes with a `structure` object (no Socra server, agent, microphone or
stored data); real Chrome plays a silent step audio so each step's state is applied when its sound
starts. The states are what the server's reducers produce (see server/tests/test_structures.py).
In exam and agent mode, dark and light, at 1440x900 and 360x640, for each of array, stack, queue,
hash table and binary search tree, it checks:
  * the structure renders its initial state, inside its panel and the viewport, with legible text (S6);
  * an operation step animates what the operation did and marks what it touched (S6);
  * the particles outline the touched element on the front canvas (S12);
  * going back to the earlier step restores exactly the earlier picture (S13);
  * the hash table shows the collision as a chain in its bucket (S7);
  * under reduced motion the final state shows at once, without animation (S6, S12).
Screenshots go to .impeccable/review/structures/ (gitignored).
"""

import base64
import io
import os
import unittest
import wave
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("SOCRA_TEST_URL", "http://localhost:5195")
SHOTS = Path(__file__).resolve().parents[2] / ".impeccable" / "review" / "structures"
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


def tree_nodes(*rows):
    return [{"key": k, "parent": p, "depth": d, "slot": s} for k, p, d, s in rows]


TREE_BEFORE = tree_nodes((1, 3, 2, 0), (3, 8, 1, 1), (8, None, 0, 2), (10, 8, 1, 3))
TREE_AFTER = tree_nodes((1, 3, 2, 0), (3, 8, 1, 1), (6, 3, 2, 2), (8, None, 0, 3), (10, 8, 1, 4))

# kind -> params, then two operation steps as the server's reducers compute them, and what the
# first step touches (data-structure-part ids) and how its parts animate.
KINDS = {
    "array": {
        "params": {"kind": "array", "items": [5, 3, 8, 1], "initial": {"kind": "array", "items": [5, 3, 8, 1], "last": None}},
        "initial_parts": ["cell:0", "cell:1", "cell:2", "cell:3"],
        "one": {"kind": "array", "items": [3, 5, 8, 1], "last": {"op": "swap", "indexes": [0, 1]}},
        "two": {"kind": "array", "items": [3, 5, 8, 1], "last": {"op": "compare", "indexes": [2, 3], "result": "greater"}},
        "touched": ["cell:0", "cell:1"],
        "anim": "slide",
        "caption": "swap [0] and [1]",
    },
    "stack": {
        "params": {"kind": "stack", "items": [1, 2], "initial": {"kind": "stack", "items": [1, 2], "last": None}},
        "initial_parts": ["cell:0", "cell:1"],
        "one": {"kind": "stack", "items": [1, 2, 3], "last": {"op": "push", "index": 2, "value": 3}},
        "two": {"kind": "stack", "items": [1, 2], "last": {"op": "pop", "index": 2, "value": 3}},
        "touched": ["cell:2"],
        "anim": "enter",
        "caption": "push 3",
    },
    "queue": {
        "params": {"kind": "queue", "items": ["a", "b"], "initial": {"kind": "queue", "items": ["a", "b"], "last": None}},
        "initial_parts": ["cell:0", "cell:1"],
        "one": {"kind": "queue", "items": ["a", "b", "c"], "last": {"op": "enqueue", "index": 2, "value": "c"}},
        "two": {"kind": "queue", "items": ["b", "c"], "last": {"op": "dequeue", "index": 0, "value": "a"}},
        "touched": ["cell:2"],
        "anim": "enter",
        "caption": 'enqueue "c"',
    },
    "hashTable": {
        "params": {
            "kind": "hashTable", "items": [12, 3], "buckets": 5, "hash": "mod",
            "initial": {"kind": "hashTable", "hash": "mod", "buckets": [[], [], [12], [3], []], "last": None},
        },
        "initial_parts": ["bucket:0", "bucket:1", "bucket:2", "entry:2:0", "bucket:3", "entry:3:0", "bucket:4"],
        "one": {
            "kind": "hashTable", "hash": "mod", "buckets": [[], [], [12, 7], [3], []],
            "last": {"op": "insert", "key": 7, "hash": 7, "bucket": 2, "position": 1, "collision": True},
        },
        "two": {
            "kind": "hashTable", "hash": "mod", "buckets": [[], [], [12, 7], [3], []],
            "last": {"op": "lookup", "key": 7, "hash": 7, "bucket": 2, "position": 1, "found": True, "probes": 2},
        },
        "touched": ["entry:2:1"],
        "anim": "enter",
        "caption": "insert 7: 7 mod 5 = bucket 2 · collision, chained after 1 key",
    },
    "tree": {
        "params": {"kind": "tree", "items": [8, 3, 10, 1], "initial": {"kind": "tree", "nodes": TREE_BEFORE, "last": None}},
        "initial_parts": ["node:1", "node:3", "node:8", "node:10"],
        "one": {"kind": "tree", "nodes": TREE_AFTER, "last": {"op": "insert", "key": 6, "path": [8, 3, 6]}},
        "two": {"kind": "tree", "nodes": TREE_AFTER, "last": {"op": "lookup", "key": 7, "path": [8, 3, 6], "found": False}},
        "touched": ["node:8", "node:3", "node:6"],
        "anim": "probe",
        "caption": "insert 6: 8 → 3 → 6",
    },
}


def scene_for(kind):
    return {
        "type": "walkthrough",
        "title": kind,
        "objects": [{"id": "ds", "primitive": "structure", "params": KINDS[kind]["params"], "hidden": False}],
        "total": 3,
    }


def step(index, say, state, seq):
    return {"index": index, "total": 3, "id": f"s{index}", "say": say, "state": {"ds": {"visible": True} | state}, "seq": seq}


# Lit-pixel reader over the particle canvases, and what is on screen for the structure.
READ = """
() => {
  const canvas = document.querySelector('[data-testid="particle-visualizer"] canvas[data-layer="front"]');
  const scale = canvas.width / innerWidth;
  const data = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
  const lit = (x, y) => {
    const px = Math.round(x * scale), py = Math.round(y * scale);
    return px >= 0 && py >= 0 && px < canvas.width && py < canvas.height && data[(py * canvas.width + px) * 4 + 3] > 40;
  };
  const root = document.querySelector('[data-structure-root]');
  const viewport = document.querySelector('[data-structure-viewport]');
  const pane = document.querySelector('[data-testid="structure-pane"]');
  const figures = document.querySelector('[data-testid="particle-visualizer"]').dataset.figures;
  if (!root) return {root: false, figures};
  const rect = (el) => { const r = el.getBoundingClientRect(); return {l: r.left, t: r.top, r: r.right, b: r.bottom, w: r.width, h: r.height}; };
  const k = root.getBoundingClientRect().width / root.viewBox.baseVal.width;
  const fonts = [...root.querySelectorAll('[data-structure-part] text')].map((el) => parseFloat(getComputedStyle(el).fontSize) * k);
  // A ring around each touched part: lit pixels in a band around its box.
  const ring = (el) => {
    const r = el.getBoundingClientRect(), m = 10;
    let border = 0;
    for (let y = Math.floor(r.top - m); y <= r.bottom + m; y++) for (let x = Math.floor(r.left - m); x <= r.right + m; x++) {
      if (lit(x, y) && !(x > r.left + 2 && x < r.right - 2 && y > r.top + 2 && y < r.bottom - 2)) border++;
    }
    return border;
  };
  const touched = [...root.querySelectorAll('[data-structure-part][data-touched="true"]')];
  const animated = [...root.querySelectorAll('[data-structure-part][data-anim]')].map((g) => {
    const anim = g.dataset.anim;
    const target = ['flash', 'probe', 'pulse'].includes(anim) ? g.querySelector('rect') : g;
    return {id: g.dataset.structurePart, anim, name: getComputedStyle(target).animationName};
  });
  const rows = [...root.querySelectorAll('[data-structure-row]')].map((row) => ({
    bucket: row.dataset.structureRow, collision: row.dataset.collision || '', active: row.dataset.active || '',
    xs: [...row.querySelectorAll('[data-structure-part^="entry:"] rect')].map((r) => r.getBoundingClientRect().left),
  }));
  return {
    root: true, figures,
    vw: innerWidth, vh: innerHeight,
    overflowX: document.documentElement.scrollWidth - innerWidth,
    svg: rect(root), viewport: rect(viewport), pane: rect(pane),
    scrolls: viewport.scrollWidth > viewport.clientWidth + 1 || viewport.scrollHeight > viewport.clientHeight + 1,
    minFont: fonts.length ? Math.min(...fonts) : 99,
    kind: root.dataset.kind, op: root.dataset.op || '', motion: root.dataset.motion,
    caption: document.querySelector('[data-structure-caption]').textContent,
    parts: [...root.querySelectorAll('[data-structure-part]')].map((el) => el.dataset.structurePart),
    touched: touched.map((el) => el.dataset.structurePart),
    rings: touched.map((el) => ring(el.querySelector('rect'))),
    animated, rows,
    ghosts: root.querySelectorAll('[data-structure-ghost]').length,
  };
}
"""

# Everything that defines the picture, to compare a step with itself after going back.
PICTURE = """
() => {
  const root = document.querySelector('[data-structure-root]');
  return root ? [...root.querySelectorAll('[data-structure-part],[data-structure-ghost],[data-structure-row]')]
    .map((el) => [el.dataset.structurePart || el.dataset.structureRow || 'ghost', el.dataset.touched || '', el.dataset.anim || '',
      el.dataset.collision || '', el.textContent].join('|')).concat([document.querySelector('[data-structure-caption]').textContent]) : null;
}
"""


class StructureTest(unittest.TestCase):
    def prepare(self, page, mode):
        page.goto(f"{BASE_URL}/?mode={mode}")
        page.get_by_test_id("particle-visualizer").wait_for()
        page.wait_for_function("window.testSockets.some(s => s.onmessage)")
        page.evaluate(
            """mode => {
              const ws = window.testSockets.find(s => s.onmessage);
              if (mode === 'agent') ws.receive({type: 'agent_started', backend: 'claude-code', model: 'sonnet', cwd: 'C:/test'});
              else ws.receive({type: 'question', index: 1, total: 1, text: 'Explain a structure.'});
              ws.receive({type: 'state', state: 'speaking'});
            }""",
            mode,
        )

    def send(self, page, message):
        page.evaluate("m => window.testSockets.find(s => s.onmessage).receive(m)", message)

    def play(self, page, step_message, wav):
        self.send(page, {"type": "tts_audio", "format": "wav", "data": wav, "step": step_message})
        self.send(page, {"type": "state", "state": "speaking"})

    def wait_figures(self, page, text):
        page.wait_for_function(
            "t => document.querySelector('[data-testid=\"particle-visualizer\"]').dataset.figures.includes(t)", arg=text, timeout=10000
        )

    def check_fits(self, info, tag):
        self.assertTrue(info["root"], f"{tag}: no structure")
        self.assertLessEqual(info["overflowX"], 1, f"{tag}: page scrolls sideways {info}")
        self.assertLessEqual(info["pane"]["r"], info["vw"] + 1, f"{tag}: panel leaves the viewport {info}")
        self.assertGreaterEqual(info["viewport"]["l"], info["pane"]["l"] - 1, f"{tag}: viewport leaves its panel {info}")
        self.assertLessEqual(info["viewport"]["r"], info["pane"]["r"] + 1, f"{tag}: viewport leaves its panel {info}")
        self.assertLessEqual(info["viewport"]["b"], info["pane"]["b"] + 1, f"{tag}: viewport leaves its panel {info}")
        if not info["scrolls"]:
            self.assertGreaterEqual(info["svg"]["l"], info["viewport"]["l"] - 1, f"{tag}: drawing leaves its viewport {info}")
            self.assertLessEqual(info["svg"]["r"], info["viewport"]["r"] + 1, f"{tag}: drawing leaves its viewport {info}")
            self.assertLessEqual(info["svg"]["b"], info["viewport"]["b"] + 1, f"{tag}: drawing leaves its viewport {info}")
        self.assertGreaterEqual(info["minFont"], MIN_FONT_PX, f"{tag}: text too small {info['minFont']:.1f}px")

    def test_every_kind_in_every_mode_theme_and_size(self):
        SHOTS.mkdir(parents=True, exist_ok=True)
        wav = silent_wav()
        with sync_playwright() as playwright:
            with playwright.chromium.launch(channel="chrome", args=["--autoplay-policy=no-user-gesture-required"]) as browser:
                for mode in ("exam", "agent"):
                    for theme in ("dark", "light"):
                        for width, height in SIZES:
                            context = browser.new_context(viewport={"width": width, "height": height})
                            try:
                                context.add_init_script(SOCKET + f"localStorage.setItem('socra_theme', '{theme}');")
                                for kind in KINDS:
                                    with self.subTest(mode=mode, theme=theme, size=(width, height), kind=kind):
                                        page = context.new_page()
                                        try:
                                            self.run_case(page, mode, kind, wav, f"{kind}-{mode}-{theme}-{width}x{height}")
                                        finally:
                                            page.close()
                            finally:
                                context.close()

    def run_case(self, page, mode, kind, wav, tag):
        spec = KINDS[kind]
        self.prepare(page, mode)
        self.send(page, scene_for(kind))

        # Step 1: an operation. It animates, marks what it touched and the particles outline it.
        self.play(page, step(1, "First operation.", spec["one"], 1), wav)
        page.locator("[data-structure-root]").wait_for()
        self.wait_figures(page, "touch:ds:")
        first = page.evaluate(READ)
        self.assertTrue(first["animated"], f"{tag}: the operation is not animated {first['animated']}")
        self.assertTrue(all(a["name"] != "none" for a in first["animated"]), f"{tag}: animation does not run {first['animated']}")
        self.assertIn(spec["anim"], [a["anim"] for a in first["animated"]], f"{tag}: expected a {spec['anim']} animation {first['animated']}")
        page.wait_for_timeout(3000)
        one = page.evaluate(READ)
        page.screenshot(path=str(SHOTS / f"{tag}-1.png"))
        self.check_fits(one, tag)
        self.assertEqual(one["kind"], kind, tag)
        self.assertEqual(sorted(one["touched"]), sorted(spec["touched"]), f"{tag}: touched parts")
        self.assertEqual(one["caption"], spec["caption"], tag)
        self.assertTrue(one["rings"] and all(r > 15 for r in one["rings"][:1]), f"{tag}: touched part is not outlined by particles {one['rings']}")
        before = page.evaluate(PICTURE)

        if kind == "hashTable":
            # Collision: 7 and 12 both hash to bucket 2, so they are chained there, left to right.
            row = next(r for r in one["rows"] if r["bucket"] == "2")
            self.assertEqual(row["collision"], "true", f"{tag}: collision is not marked")
            self.assertEqual(len(row["xs"]), 2, f"{tag}: chain {row}")
            self.assertLess(row["xs"][0], row["xs"][1], f"{tag}: chain order {row}")
            self.assertTrue(all(r["collision"] == "" for r in one["rows"] if r["bucket"] != "2"), tag)

        # Step 2: another operation changes the picture.
        self.play(page, step(2, "Second operation.", spec["two"], 2), wav)
        page.wait_for_function("op => document.querySelector('[data-structure-root]').dataset.op === op", arg=spec["two"]["last"]["op"])
        page.wait_for_timeout(2500)
        two = page.evaluate(READ)
        page.screenshot(path=str(SHOTS / f"{tag}-2.png"))
        self.check_fits(two, tag)
        self.assertEqual(two["op"], spec["two"]["last"]["op"], tag)
        self.assertNotEqual(page.evaluate(PICTURE), before, f"{tag}: step 2 looks like step 1")

        # Back to step 1 restores exactly the earlier picture.
        self.play(page, step(1, "First operation.", spec["one"], 3), wav)
        page.wait_for_function("op => document.querySelector('[data-structure-root]').dataset.op === op", arg=spec["one"]["last"]["op"])
        self.assertEqual(page.evaluate(PICTURE), before, f"{tag}: back differs")

    def test_the_initial_contents_render_inside_the_panel(self):
        SHOTS.mkdir(parents=True, exist_ok=True)
        wav = silent_wav()
        with sync_playwright() as playwright:
            with playwright.chromium.launch(channel="chrome", args=["--autoplay-policy=no-user-gesture-required"]) as browser:
                for kind, spec in KINDS.items():
                    with self.subTest(kind=kind):
                        context = browser.new_context(viewport={"width": 360, "height": 640})
                        try:
                            context.add_init_script(SOCKET)
                            page = context.new_page()
                            self.prepare(page, "agent")
                            self.send(page, scene_for(kind))
                            # Before any step speaks, the structure is drawn from the initial state in its params.
                            page.locator("[data-structure-root]").wait_for()
                            self.assertEqual(page.evaluate(READ)["parts"], spec["initial_parts"], kind)
                            # A first step that does nothing to it draws the same contents.
                            self.play(page, step(1, "Here it is.", spec["params"]["initial"], 1), wav)
                            page.wait_for_timeout(800)
                            info = page.evaluate(READ)
                            page.screenshot(path=str(SHOTS / f"{kind}-initial-360x640.png"))
                            self.assertEqual(info["parts"], spec["initial_parts"], kind)
                            self.assertEqual(info["touched"], [], kind)
                            self.assertEqual(info["caption"], "", kind)
                            self.check_fits(info, kind)
                        finally:
                            context.close()

    def test_reduced_motion_shows_the_final_state_without_animation(self):
        wav = silent_wav()
        with sync_playwright() as playwright:
            with playwright.chromium.launch(channel="chrome", args=["--autoplay-policy=no-user-gesture-required"]) as browser:
                for kind in ("hashTable", "tree", "stack"):
                    with self.subTest(kind=kind):
                        context = browser.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
                        try:
                            context.add_init_script(SOCKET)
                            page = context.new_page()
                            spec = KINDS[kind]
                            self.prepare(page, "agent")
                            self.send(page, scene_for(kind))
                            self.play(page, step(1, "First operation.", spec["one"], 1), wav)
                            page.locator("[data-structure-root][data-op]").wait_for()
                            info = page.evaluate(READ)
                            self.assertEqual(info["motion"], "reduced")
                            self.assertEqual(info["animated"], [], f"animated under reduced motion {info['animated']}")
                            self.assertEqual(sorted(info["touched"]), sorted(spec["touched"]))
                            self.assertEqual(info["ghosts"], 0)
                            self.wait_figures(page, "touch:ds:")
                            # A pop would leave a ghost with full motion; here the final state is drawn at once.
                            self.play(page, step(2, "Second operation.", spec["two"], 2), wav)
                            page.wait_for_function("op => document.querySelector('[data-structure-root]').dataset.op === op", arg=spec["two"]["last"]["op"])
                            after = page.evaluate(READ)
                            self.assertEqual(after["ghosts"], 0)
                            self.assertEqual(after["animated"], [])
                        finally:
                            context.close()

    def test_a_long_chain_scrolls_rather_than_shrinking_the_text(self):
        wav = silent_wav()
        keys = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50]
        buckets = [keys, [], [], [], []]
        params = {
            "kind": "hashTable", "items": keys, "buckets": 5, "hash": "mod",
            "initial": {"kind": "hashTable", "hash": "mod", "buckets": buckets, "last": None},
        }
        scene = {"type": "walkthrough", "title": "Chain", "objects": [{"id": "ds", "primitive": "structure", "params": params, "hidden": False}], "total": 1}
        state = {"kind": "hashTable", "hash": "mod", "buckets": buckets, "last": {"op": "insert", "key": 50, "hash": 50, "bucket": 0, "position": 9, "collision": True}}
        with sync_playwright() as playwright:
            with playwright.chromium.launch(channel="chrome", args=["--autoplay-policy=no-user-gesture-required"]) as browser:
                context = browser.new_context(viewport={"width": 360, "height": 640})
                try:
                    context.add_init_script(SOCKET)
                    page = context.new_page()
                    self.prepare(page, "agent")
                    self.send(page, scene)
                    self.play(page, step(1, "A long chain.", state, 1), wav)
                    page.locator("[data-structure-root][data-op]").wait_for()
                    page.wait_for_timeout(1500)
                    info = page.evaluate(READ)
                    SHOTS.mkdir(parents=True, exist_ok=True)
                    page.screenshot(path=str(SHOTS / "long-chain-360x640.png"))
                    self.assertLessEqual(info["overflowX"], 1, info)
                    self.assertGreaterEqual(info["minFont"], MIN_FONT_PX, info)
                    self.assertTrue(info["scrolls"], "a ten-key chain should scroll sideways, not shrink")
                finally:
                    context.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
