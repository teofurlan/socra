"""The page socket carries whole utterances as base64 WAV (review R3-partial-payload-size)."""
from __future__ import annotations

from socra_server.entrypoints import ws_server


def test_the_page_server_accepts_a_long_push_to_talk_utterance(monkeypatch):
    seen = {}

    def fake_serve(*args, **kwargs):
        seen.update(kwargs)
        return object()

    monkeypatch.setattr(ws_server, "serve", fake_serve)
    ws_server.serve_pages(port=0)

    # 30 s at 48 kHz, 16-bit mono, base64: about 3.8 MB; the websockets default (1 MiB)
    # would close the connection about 8 s into a push-to-talk turn.
    thirty_seconds_b64 = 30 * 48000 * 2 * 4 // 3
    assert seen["max_size"] >= 2 * thirty_seconds_b64
