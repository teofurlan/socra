"""Whisper STT adapter — wraps dictation.transcriber.WhisperTranscriber from the voice stack."""
from __future__ import annotations

import io
import logging
import os
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import soundfile as sf

from socra_server.domain.speech import SPEECH_LANGUAGE

SILENCE_HALLUCINATIONS: tuple[str, ...] = (
    "subtítulos realizados por",
    "amara.org",
    "gracias por ver",
    "suscríbete",
)

DEFAULT_WHISPER_MODEL = "large-v3-turbo"


def get_whisper_config() -> tuple[str, str | None, str | None]:
    """Return (model_size, device, compute_type) from environment or defaults."""
    model_size = os.environ.get("SOCRA_WHISPER_MODEL", DEFAULT_WHISPER_MODEL).strip()
    device_env = os.environ.get("SOCRA_WHISPER_DEVICE", "").strip().lower()

    device = None
    compute_type = None
    if device_env == "cuda":
        device = "cuda"
        compute_type = "float16"
    elif device_env == "cpu":
        device = "cpu"
        compute_type = "int8"
    elif device_env and device_env != "auto":
        device = device_env

    return model_size, device, compute_type


def _ensure_cuda_dlls() -> None:
    """Ensure CUDA runtime DLLs (e.g. cublas64_12.dll) are accessible on Windows."""
    if sys.platform != "win32":
        return
    candidate_dirs = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "lib" / "ollama" / "cuda_v12",
        Path(sys.prefix) / "Lib" / "site-packages" / "torch" / "lib",
        Path("C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.0/bin"),
        Path("C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.1/bin"),
        Path("C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.2/bin"),
        Path("C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.3/bin"),
        Path("C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.4/bin"),
    ]
    for d in candidate_dirs:
        if (d / "cublas64_12.dll").is_file():
            d_str = str(d.resolve())
            if d_str not in os.environ.get("PATH", ""):
                os.environ["PATH"] = d_str + os.pathsep + os.environ.get("PATH", "")
            if hasattr(os, "add_dll_directory"):
                try:
                    os.add_dll_directory(d_str)
                except Exception:
                    pass
            break



def is_valid_answer(text: str) -> bool:
    """Validate whether transcribed text represents a meaningful answer.

    Treat as no answer:
    1. Text empty once punctuation/whitespace is stripped.
    2. One token making >= 60% of >= 4 tokens.
    3. Known silence hallucination phrases (case-insensitive substring).
    """
    if not text:
        return False
    stripped = re.sub(r"[\W_]+", "", text)
    if not stripped:
        return False

    text_lower = text.lower()
    for phrase in SILENCE_HALLUCINATIONS:
        if phrase in text_lower:
            return False

    raw_tokens = text.split()
    tokens = [re.sub(r"[\W_]+", "", t).lower() for t in raw_tokens]
    tokens = [t for t in tokens if t]
    if len(tokens) >= 4:
        counts = Counter(tokens)
        max_freq = max(counts.values())
        if max_freq / len(tokens) >= 0.6:
            return False

    return True


def _voice_stack_dir() -> Path:
    env = os.environ.get("VOICE_STACK_DIR")
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve()
    repo_root = here.parents[4]
    return (repo_root / "voice").resolve()


def _wav_bytes_to_array(wav_bytes: bytes) -> "np.ndarray":
    """Decode WAV bytes to a 16 kHz float32 numpy array (mono)."""
    buf = io.BytesIO(wav_bytes)
    data, sr = sf.read(buf)
    if data.ndim > 1:
        data = data.mean(axis=1)
    if sr != 16000:
        duration = len(data) / sr
        target_len = int(duration * 16000)
        if target_len > 0:
            data = np.interp(
                np.linspace(0, len(data), target_len, endpoint=False),
                np.arange(len(data)),
                data,
            )
    return data.astype(np.float32)


class WhisperSTT:
    """Lazy-loading faster-whisper adapter.

    Call ``load()`` in a background thread; ``transcribe()`` is then safe to
    call from ``asyncio.to_thread``.

    ``initial_prompt`` is built from ``glossary_terms`` (the keys from
    pi_voice/terms.json) merged with any per-call ``glossary`` list.
    """

    def __init__(self, glossary_terms: list[str] | None = None) -> None:
        self._transcriber = None
        # Base glossary terms from the voice stack (set by the loader)
        self._base_terms: list[str] = glossary_terms or []
        self._model_size: str = DEFAULT_WHISPER_MODEL

    def set_base_terms(self, terms: list[str]) -> None:
        self._base_terms = terms

    def load(self) -> None:
        """Load the Whisper model.  Must be called from a background thread."""
        _ensure_cuda_dlls()
        stack_dir = _voice_stack_dir()
        if str(stack_dir) not in sys.path:
            sys.path.insert(0, str(stack_dir))

        from dictation.transcriber import WhisperTranscriber  # type: ignore[import]

        model_size, device, compute_type = get_whisper_config()
        self._model_size = model_size
        self._transcriber = WhisperTranscriber(
            model_size=model_size,
            device=device,
            compute_type=compute_type,
        )

    def _build_prompt(self, extra_glossary: list[str] | None) -> str:
        """Combine base terms and any per-call extra terms into an initial_prompt string."""
        combined = list(self._base_terms)
        if extra_glossary:
            for term in extra_glossary:
                if term not in combined:
                    combined.append(term)
        return ", ".join(combined)

    def transcribe(self, wav_bytes: bytes, prompt: str = "") -> str:
        """Transcribe WAV bytes to text.

        ``prompt`` is used as the Whisper initial_prompt when provided;
        otherwise the glossary-derived prompt is used.  Raises RuntimeError if
        not yet loaded.
        """
        if self._transcriber is None:
            raise RuntimeError("WhisperSTT not loaded — call load() first")

        audio_array = _wav_bytes_to_array(wav_bytes)
        if audio_array.size == 0:
            return ""

        # Use the underlying faster-whisper model directly so we can pass
        # initial_prompt, language, and vad_filter (S4: never call Ollama cleaner).
        initial_prompt = prompt if prompt else self._build_prompt(None)

        try:
            segments, _info = self._transcriber.model.transcribe(
                audio_array,
                language=SPEECH_LANGUAGE,
                vad_filter=True,
                initial_prompt=initial_prompt or None,
            )
            parts = []
            for seg in segments:
                text = seg.text.strip()
                if not text:
                    continue
                no_speech = getattr(seg, "no_speech_prob", 0.0)
                avg_logprob = getattr(seg, "avg_logprob", 0.0)
                if no_speech > 0.6 and avg_logprob < -1.0:
                    continue
                parts.append(text)
            joined = " ".join(parts).strip()
            if not is_valid_answer(joined):
                return ""
            return joined
        except Exception:
            # CUDA can initialize successfully yet fail on the first inference
            # when runtime DLLs are missing. Preserve the stack's CPU fallback
            # without losing initial_prompt or fabricating an empty answer.
            if getattr(self._transcriber, "device", "cpu") == "cpu":
                raise
            logging.getLogger(__name__).warning("Whisper inference failed; falling back to CPU", exc_info=True)
            fallback_cls = type(self._transcriber)
            try:
                self._transcriber = fallback_cls(
                    model_size=self._model_size,
                    device="cpu",
                    compute_type="int8",
                    download_root=self._transcriber.download_root,
                )
            except TypeError:
                self._transcriber = fallback_cls(
                    device="cpu",
                    compute_type="int8",
                    download_root=self._transcriber.download_root,
                )
            return self.transcribe(wav_bytes, prompt=initial_prompt)

    def transcribe_with_glossary(
        self, wav_bytes: bytes, extra_glossary: list[str] | None = None
    ) -> str:
        """Transcribe with base terms + optional extra glossary as initial_prompt."""
        prompt = self._build_prompt(extra_glossary)
        return self.transcribe(wav_bytes, prompt=prompt)
