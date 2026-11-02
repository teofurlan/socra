"""Readiness and connection replacement regressions."""
import asyncio
import json
import threading

import pytest

from socra_server.app import ModelLoader, PageChannel


@pytest.mark.asyncio
async def test_readiness_is_awaited_and_loading_runs_off_loop(monkeypatch):
    loader = ModelLoader()
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = threading.Event()
    threads = []

    def load_tts():
        threads.append(threading.get_ident())
        loop.call_soon_threadsafe(started.set)
        assert release.wait(3)

    def load_stt():
        threads.append(threading.get_ident())

    monkeypatch.setattr(loader.tts, "load", load_tts)
    monkeypatch.setattr(loader.stt, "load", load_stt)
    loader.attach_loop(loop)
    loader.start()
    ready = asyncio.create_task(loader.ready())
    try:
        await asyncio.wait_for(started.wait(), 1)
        assert not ready.done()
    finally:
        release.set()
    await asyncio.wait_for(ready, 1)
    assert len(threads) == 2
    assert all(thread != threading.get_ident() for thread in threads)


@pytest.mark.asyncio
async def test_failure_sending_to_old_page_does_not_disconnect_replacement():
    entered = asyncio.Event()
    release = asyncio.Event()

    class OldPage:
        async def send(self, data):
            entered.set()
            await release.wait()
            raise ConnectionError("old page closed")

    messages = []

    class NewPage:
        async def send(self, data):
            messages.append(json.loads(data))

    channel = PageChannel()
    loop = asyncio.get_running_loop()
    channel.set_connection(OldPage(), loop)
    pending = asyncio.create_task(channel.send({"type": "state", "state": "speaking"}))
    await entered.wait()
    channel.set_connection(NewPage(), loop)
    release.set()
    await pending
    assert channel.is_connected
    await channel.send({"type": "state", "state": "listening"})
    assert messages == [{"type": "state", "state": "listening"}]


@pytest.mark.asyncio
async def test_ready_retries_after_failed_load_when_resources_become_available(monkeypatch):
    loader = ModelLoader()
    loop = asyncio.get_running_loop()
    loader.attach_loop(loop)

    attempts = 0

    def mock_load_tts():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("mkl_malloc: failed to allocate memory")

    def mock_load_stt():
        pass

    monkeypatch.setattr(loader.tts, "load", mock_load_tts)
    monkeypatch.setattr(loader.stt, "load", mock_load_stt)

    # First attempt (simulated startup or initial tool call) fails
    loader.start()
    with pytest.raises(RuntimeError, match="Model loading failed: mkl_malloc"):
        await loader.ready()

    assert attempts == 1

    # Second attempt (later tool call once memory is free): must retry and succeed
    await loader.ready()
    assert attempts == 2


@pytest.mark.asyncio
async def test_concurrent_ready_calls_share_single_retry(monkeypatch):
    loader = ModelLoader()
    loop = asyncio.get_running_loop()
    loader.attach_loop(loop)

    attempts = 0

    def mock_load_tts():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("mkl_malloc: failed to allocate memory")

    def mock_load_stt():
        pass

    monkeypatch.setattr(loader.tts, "load", mock_load_tts)
    monkeypatch.setattr(loader.stt, "load", mock_load_stt)

    loader.start()
    with pytest.raises(RuntimeError, match="Model loading failed"):
        await loader.ready()

    # Multiple tool calls arrive concurrently
    t1 = asyncio.create_task(loader.ready())
    t2 = asyncio.create_task(loader.ready())
    await asyncio.gather(t1, t2)

    assert attempts == 2  # exactly one retry, not two concurrent loads


@pytest.mark.asyncio
async def test_ready_starts_loading_if_start_was_never_called(monkeypatch):
    loader = ModelLoader()
    loop = asyncio.get_running_loop()
    loader.attach_loop(loop)

    called = False

    def mock_load_tts():
        nonlocal called
        called = True

    monkeypatch.setattr(loader.tts, "load", mock_load_tts)
    monkeypatch.setattr(loader.stt, "load", lambda: None)

    # Note: loader.start() is NOT called
    await loader.ready()

    assert called
    assert loader._loaded


@pytest.mark.asyncio
async def test_ready_returns_immediately_when_already_loaded(monkeypatch):
    loader = ModelLoader()
    loader._loaded = True

    calls = 0

    def mock_load():
        nonlocal calls
        calls += 1

    monkeypatch.setattr(loader.tts, "load", mock_load)
    monkeypatch.setattr(loader.stt, "load", mock_load)

    await loader.ready()
    await loader.ready()

    assert calls == 0


@pytest.mark.asyncio
async def test_multiple_sequential_failures_can_each_retry_until_success(monkeypatch):
    loader = ModelLoader()
    loop = asyncio.get_running_loop()
    loader.attach_loop(loop)

    attempts = 0

    def mock_load_tts():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("first failure")
        if attempts == 2:
            raise RuntimeError("second failure")

    monkeypatch.setattr(loader.tts, "load", mock_load_tts)
    monkeypatch.setattr(loader.stt, "load", lambda: None)

    loader.start()
    with pytest.raises(RuntimeError, match="first failure"):
        await loader.ready()

    with pytest.raises(RuntimeError, match="second failure"):
        await loader.ready()

    await loader.ready()
    assert attempts == 3
    assert loader._loaded
