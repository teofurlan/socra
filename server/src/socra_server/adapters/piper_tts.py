"""Piper TTS adapter: speaks the reply with the catalogue voice (glossary terms in English phonemes when the language asks)."""
from __future__ import annotations

import io
import logging
import math
import os
import threading
import wave
from pathlib import Path
from typing import Any, Callable

from socra_server.domain.glossary import load_glossary, speech_segments
from socra_server.domain.speakable import speakable_text
from socra_server.domain.speech import SPEECH_ENGLISH_TERMS, TERM_PHONEME_LANGUAGE
from socra_server.domain.voices import DEFAULT_VOICE_ID, Voice, get_voice

logger = logging.getLogger(__name__)

MODEL_REPO = "rhasspy/piper-voices"
# Silence put before every clip. The page's audio output can lose the first few tens of
# milliseconds when sound starts after a pause; English Piper voices speak from their first
# samples, so without this lead-in the first phoneme is cut (daniela's own 30-75 ms of
# silence used to hide it).
LEAD_IN_MS = 80
LENGTH_SCALE_ENV = "SOCRA_TTS_LENGTH_SCALE"


def _voice_stack_dir() -> Path:
    env = os.environ.get("VOICE_STACK_DIR")
    if env:
        return Path(env).resolve()
    # server/src/socra_server/adapters/piper_tts.py -> repo root is 4 levels up
    repo_root = Path(__file__).resolve().parents[4]
    return (repo_root / "voice").resolve()


def _download_voice(voice: Voice) -> Any:
    """Fetch (or reuse from the Hugging Face cache) and load a Piper model."""
    from huggingface_hub import hf_hub_download
    from piper import PiperVoice

    onnx_path = hf_hub_download(MODEL_REPO, f"{voice.model}.onnx")
    hf_hub_download(MODEL_REPO, f"{voice.model}.onnx.json")  # must sit next to the model
    return PiperVoice.load(onnx_path)


def _length_scale(voice: Voice) -> float:
    """The catalogue pace, unless SOCRA_TTS_LENGTH_SCALE holds a valid override."""
    raw = os.environ.get(LENGTH_SCALE_ENV)
    if raw is None or not raw.strip():
        return voice.length_scale
    try:
        value = float(raw)
    except ValueError:
        value = math.nan
    if not math.isfinite(value) or value <= 0:
        logger.warning("Ignoring invalid %s=%r; using %s", LENGTH_SCALE_ENV, raw, voice.length_scale)
        return voice.length_scale
    return value


class PiperTTS:
    """Lazy-loading Piper TTS adapter.

    Call ``load()`` in a background thread before first use. ``voice_loader``,
    ``phonemizer`` and ``glossary_path`` are seams for tests; by default they
    use the real model download, espeak and the voice stack's terms.json.
    """

    def __init__(
        self,
        voice_loader: Callable[[Voice], Any] | None = None,
        phonemizer: Any | None = None,
        glossary_path: Path | str | None = None,
    ) -> None:
        self._voice_loader = voice_loader or _download_voice
        self._phonemizer = phonemizer
        self._glossary_path = glossary_path
        self._glossary: dict[str, str] = {}
        self._voice_id: str = DEFAULT_VOICE_ID
        self._voices: dict[str, Any] = {}
        self._loaded = False
        self._lock = threading.Lock()

    def load(self) -> None:
        """Load the current voice and the glossary.  Must be called from a background thread."""
        if SPEECH_ENGLISH_TERMS and self._phonemizer is None:
            from piper.phonemize_espeak import EspeakPhonemizer

            self._phonemizer = EspeakPhonemizer()
        path = self._glossary_path or _voice_stack_dir() / "pi_voice" / "terms.json"
        self._glossary = load_glossary(path)
        self._piper_voice(self._current_voice())
        self._loaded = True

    @property
    def voice_id(self) -> str:
        """Current voice ID."""
        return self._voice_id

    def set_voice(self, voice_id: object) -> bool:
        """Set the current voice. Returns False if unknown, True otherwise."""
        voice = get_voice(voice_id)
        if voice is None:
            return False
        self._voice_id = voice.id
        return True

    @property
    def glossary_terms(self) -> list[str]:
        """Written glossary terms (loaded after load()), used to prime the recognizer."""
        return list(self._glossary)

    def synthesize(self, text: str) -> bytes:
        """Return WAV bytes, or b"" when nothing is speakable.  Raises RuntimeError if not yet loaded."""
        if not self._loaded:
            raise RuntimeError("PiperTTS not loaded — call load() first")
        spoken = speakable_text(text)
        if not spoken:
            return b""

        from piper import SynthesisConfig

        voice = self._current_voice()
        piper_voice = self._piper_voice(voice)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            piper_voice.synthesize_wav(
                self._with_english_phonemes(spoken) if SPEECH_ENGLISH_TERMS else spoken,
                wav_file,
                syn_config=SynthesisConfig(length_scale=_length_scale(voice), speaker_id=voice.speaker),
            )
        return _with_lead_in(buffer.getvalue())

    def _current_voice(self) -> Voice:
        voice = get_voice(self._voice_id)
        assert voice is not None  # set_voice only accepts catalogue ids
        return voice

    def _piper_voice(self, voice: Voice) -> Any:
        with self._lock:
            if voice.id not in self._voices:
                self._voices[voice.id] = self._voice_loader(voice)
            return self._voices[voice.id]

    def _with_english_phonemes(self, text: str) -> str:
        """Keep the text as written and inline each glossary match as Piper raw phonemes."""
        parts = []
        for segment in speech_segments(text, self._glossary):
            if segment["language"] == TERM_PHONEME_LANGUAGE:
                phonemes = self._phonemes(segment["spoken"])
                parts.append(f"[[ {phonemes} ]]" if phonemes else segment["text"])
            else:
                parts.append(segment["text"])
        return "".join(parts)

    def _phonemes(self, spoken: str) -> str:
        sentences = self._phonemizer.phonemize(TERM_PHONEME_LANGUAGE, spoken)
        return " ".join("".join(sentence) for sentence in sentences).strip()


def _with_lead_in(wav_bytes: bytes) -> bytes:
    """Return the same WAV with LEAD_IN_MS of silence before its first sample."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as source:
        params = source.getparams()
        frames = source.readframes(source.getnframes())
    lead = round(params.framerate * LEAD_IN_MS / 1000)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as padded:
        padded.setnchannels(params.nchannels)
        padded.setsampwidth(params.sampwidth)
        padded.setframerate(params.framerate)
        padded.writeframes(bytes(lead * params.nchannels * params.sampwidth) + frames)
    return buffer.getvalue()
