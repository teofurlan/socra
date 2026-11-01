"""Whisper inference failure regressions without loading real models."""
from types import SimpleNamespace

import pytest

from socra_server.adapters.whisper_stt import WhisperSTT
from tests.conftest import make_wav_bytes


def test_cuda_runtime_failure_retries_on_cpu_with_same_prompt():
    calls = []

    class Transcriber:
        def __init__(self, device="cuda", compute_type="float16", download_root="cached"):
            self.device = device
            self.download_root = download_root
            self.model = self

        def transcribe(self, audio, **kwargs):
            calls.append((self.device, kwargs))

            def segments():
                if self.device == "cuda":
                    raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")
                yield SimpleNamespace(text="A process has its own memory.")

            return segments(), None

    stt = WhisperSTT(["API"])
    stt._transcriber = Transcriber()
    assert stt.transcribe_with_glossary(make_wav_bytes(), ["thread"]) == "A process has its own memory."
    assert calls == [
        ("cuda", {"language": "en", "vad_filter": True, "initial_prompt": "API, thread, Socra"}),
        ("cpu", {"language": "en", "vad_filter": True, "initial_prompt": "API, thread, Socra"}),
    ]


def test_cpu_inference_failure_is_not_returned_as_a_final_empty_answer():
    def broken(*args, **kwargs):
        raise RuntimeError("inference failed")

    stt = WhisperSTT()
    stt._transcriber = SimpleNamespace(device="cpu", model=SimpleNamespace(transcribe=broken))
    with pytest.raises(RuntimeError, match="inference failed"):
        stt.transcribe_with_glossary(make_wav_bytes())
