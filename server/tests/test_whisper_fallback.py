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


def test_warm_up_runs_one_full_decode_without_vad_so_the_first_turn_is_not_cold():  # live S3
    calls = []

    class Model:
        def transcribe(self, audio, **kwargs):
            calls.append((len(audio), kwargs))
            return iter([SimpleNamespace(text="")]), None

    stt = WhisperSTT()
    stt._transcriber = SimpleNamespace(device="cuda", model=Model())
    stt.warm_up()

    # VAD would drop the silence and skip the decoder, leaving it cold.
    assert len(calls) == 1 and calls[0][1]["vad_filter"] is False


def test_warm_up_failure_never_raises():
    def broken(*args, **kwargs):
        raise RuntimeError("cublas missing")

    stt = WhisperSTT()
    stt._transcriber = SimpleNamespace(device="cuda", model=SimpleNamespace(transcribe=broken))
    stt.warm_up()  # the first real turn falls back to CPU as before
    WhisperSTT().warm_up()  # not loaded: nothing to warm
