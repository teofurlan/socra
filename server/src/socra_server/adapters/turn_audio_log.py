"""Opt-in diagnostic: keep each spoken turn with its transcript to evaluate recognition offline."""
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

SAVE_DIR_ENV = "SOCRA_STT_SAVE_DIR"


def save_turn_audio(wav_bytes: bytes, transcript: str) -> None:
    """Write ``<stamp>.wav`` and ``<stamp>.txt`` into SOCRA_STT_SAVE_DIR; do nothing when it is unset.

    A failure is logged and swallowed: diagnostics never break a turn.
    """
    raw = os.environ.get(SAVE_DIR_ENV, "").strip()
    if not raw:
        return
    try:
        folder = Path(raw)
        folder.mkdir(parents=True, exist_ok=True)
        stem = folder / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        stem.with_suffix(".wav").write_bytes(wav_bytes)
        stem.with_suffix(".txt").write_text(transcript, encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not save turn audio to %s: %s", raw, exc)
