"""Desktop launcher: the shortcut script and running without a console (pythonw)."""
from __future__ import annotations

import asyncio
import contextlib
import subprocess
import sys
from pathlib import Path

import pytest

from socra_server import __main__ as main_mod

SERVER_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SERVER_DIR / "install-shortcut.ps1"
windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows shortcut")


def test_missing_console_streams_go_to_a_log_file(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    main_mod._ensure_streams(tmp_path)
    print("hello from pythonw")
    sys.stderr.write("progress bar\n")
    sys.stdout.flush()

    log = (tmp_path / "socra-agent.log").read_text(encoding="utf-8")
    assert "hello from pythonw" in log and "progress bar" in log


def test_console_streams_are_left_alone(monkeypatch, tmp_path):
    stdout, stderr = sys.stdout, sys.stderr

    main_mod._ensure_streams(tmp_path)

    assert sys.stdout is stdout and sys.stderr is stderr
    assert not (tmp_path / "socra-agent.log").exists()


def _powershell(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), *args],
        capture_output=True, text=True, timeout=60,
    )


def _read_shortcut(path: Path) -> dict[str, str]:
    script = (
        f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{path}'); "
        "Write-Output $s.TargetPath; Write-Output $s.Arguments; Write-Output $s.WorkingDirectory"
    )
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=60
    ).stdout.splitlines()
    return {"target": out[0], "arguments": out[1], "workdir": out[2]}


@windows_only
def test_shortcut_starts_agent_mode_without_a_console(tmp_path):
    result = _powershell("-Destination", str(tmp_path))

    assert result.returncode == 0, result.stderr
    shortcut = _read_shortcut(tmp_path / "Socra.lnk")
    assert Path(shortcut["target"]) == SERVER_DIR / ".venv" / "Scripts" / "pythonw.exe"
    assert shortcut["arguments"] == "-m socra_server --agent"
    assert Path(shortcut["workdir"]) == SERVER_DIR


@windows_only
def test_shortcut_can_be_removed(tmp_path):
    assert _powershell("-Destination", str(tmp_path)).returncode == 0

    result = _powershell("-Destination", str(tmp_path), "-Remove")

    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "Socra.lnk").exists()


class _Channel:
    def __init__(self, connected: bool) -> None:
        self.is_connected = connected


async def test_idle_watch_ends_when_no_agent_page_is_connected():
    await asyncio.wait_for(main_mod._idle_watch(_Channel(False), idle_s=0.05, poll_s=0.01), timeout=1)


async def test_idle_watch_waits_while_a_page_is_connected():
    channel = _Channel(True)
    watch = asyncio.create_task(main_mod._idle_watch(channel, idle_s=0.05, poll_s=0.01))

    await asyncio.sleep(0.15)
    assert not watch.done()

    channel.is_connected = False
    await asyncio.wait_for(watch, timeout=1)


async def test_standalone_stops_and_frees_the_ports_when_idle(monkeypatch):
    events: list[str] = []

    class FakeAgent:
        channel = _Channel(False)

        async def shutdown(self):
            events.append("agent shutdown")

    class FakeLoader:
        def start(self):
            events.append("models loading")

    async def not_running(host, port):
        return False

    class FakeServer:
        async def serve_forever(self):
            await asyncio.Future()

    @contextlib.asynccontextmanager
    async def fake_serve_page():
        events.append("http up")
        yield FakeServer()
        events.append("http down")

    async def fake_ws_forever():
        try:
            await asyncio.Future()
        finally:
            events.append("ws down")

    monkeypatch.setattr(main_mod, "server_running", not_running)
    monkeypatch.setattr(main_mod, "_build_apps", lambda loop: (None, FakeAgent(), FakeLoader()))
    monkeypatch.setattr(main_mod.http_server, "serve_page", fake_serve_page)
    monkeypatch.setattr(main_mod.ws_server, "serve_forever", fake_ws_forever)

    await asyncio.wait_for(main_mod._standalone(launch=lambda url: None, idle_s=0.05, poll_s=0.01), timeout=2)

    assert events[-3:] == ["http down", "ws down", "agent shutdown"]


# --- The desktop shortcut runs under pythonw, which has no console. ----------------------

class _Kernel32:
    """Records console calls; ``window`` is what GetConsoleWindow returns."""

    def __init__(self, window: int) -> None:
        self.window = window
        self.calls: list[tuple] = []

    def GetConsoleWindow(self) -> int:
        self.calls.append(("GetConsoleWindow",))
        return self.window

    def AllocConsole(self) -> int:
        self.calls.append(("AllocConsole",))
        self.window = 4242
        return 1


class _User32:
    def __init__(self, kernel32: _Kernel32) -> None:
        self.kernel32 = kernel32

    def ShowWindow(self, hwnd: int, cmd: int) -> int:
        self.kernel32.calls.append(("ShowWindow", hwnd, cmd))
        return 1


def test_without_a_console_children_share_one_hidden_console():
    # Pi and the Claude CLI are console programs: started from pythonw, each would open
    # its own terminal window, and closing that window would kill it.
    kernel32 = _Kernel32(window=0)

    main_mod._hide_console_for_children(kernel32, _User32(kernel32), platform="win32")

    assert kernel32.calls == [("GetConsoleWindow",), ("AllocConsole",), ("GetConsoleWindow",), ("ShowWindow", 4242, 0)]


def test_a_visible_console_is_left_alone():
    kernel32 = _Kernel32(window=77)  # started from a terminal: keep it as it is

    main_mod._hide_console_for_children(kernel32, _User32(kernel32), platform="win32")

    assert kernel32.calls == [("GetConsoleWindow",)]


def test_other_platforms_do_nothing():
    kernel32 = _Kernel32(window=0)

    main_mod._hide_console_for_children(kernel32, _User32(kernel32), platform="linux")

    assert kernel32.calls == []


def test_closing_the_page_stops_agent_mode_quickly_by_default():
    # A reload reconnects within a couple of seconds; a closed page should not keep Socra
    # running for minutes.
    assert main_mod.DEFAULT_AGENT_IDLE_S <= 15
