"""Unit tests for socra-server setup (Issue #93)."""
from __future__ import annotations

from pathlib import Path
import subprocess
from unittest.mock import MagicMock

import pytest

from socra_server import setup


def test_check_prerequisites_all_ok(monkeypatch):
    def fake_which(cmd):
        return f"/mock/bin/{cmd}"

    monkeypatch.setattr(setup.shutil, "which", fake_which)

    def fake_runner(cmd, **kwargs):
        name = Path(cmd[0]).name
        if name == "uv":
            return subprocess.CompletedProcess(cmd, 0, stdout="uv 0.5.0\n", stderr="")
        if name == "node":
            return subprocess.CompletedProcess(cmd, 0, stdout="v22.12.0\n", stderr="")
        if name == "pnpm":
            return subprocess.CompletedProcess(cmd, 0, stdout="9.15.0\n", stderr="")
        if name == "claude":
            return subprocess.CompletedProcess(cmd, 0, stdout="claude 0.2.0\n", stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="unknown")

    results = setup.check_prerequisites(runner=fake_runner)
    assert len(results) == 4
    assert all(r.ok for r in results)


def test_check_prerequisites_missing_tool(monkeypatch):
    def fake_which(cmd):
        if cmd == "pnpm":
            return None
        return f"/mock/bin/{cmd}"

    monkeypatch.setattr(setup.shutil, "which", fake_which)

    def fake_runner(cmd, **kwargs):
        name = Path(cmd[0]).name
        if name == "node":
            return subprocess.CompletedProcess(cmd, 0, stdout="v22.0.0\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="1.0.0\n", stderr="")

    results = setup.check_prerequisites(runner=fake_runner)
    pnpm_res = next(r for r in results if r.name == "pnpm")
    assert not pnpm_res.ok
    assert "not found" in pnpm_res.error_message
    assert pnpm_res.install_guide is not None


def test_check_prerequisites_node_too_old(monkeypatch):
    def fake_which(cmd):
        return f"/mock/bin/{cmd}"

    monkeypatch.setattr(setup.shutil, "which", fake_which)

    def fake_runner(cmd, **kwargs):
        name = Path(cmd[0]).name
        if name == "node":
            return subprocess.CompletedProcess(cmd, 0, stdout="v18.19.0\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="1.0.0\n", stderr="")

    results = setup.check_prerequisites(runner=fake_runner)
    node_res = next(r for r in results if r.name == "node")
    assert not node_res.ok
    assert "below required" in node_res.error_message


def test_build_web_app(tmp_path):
    calls = []

    def fake_runner(cmd, **kwargs):
        calls.append((cmd, kwargs.get("cwd")))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    ok = setup.build_web_app(tmp_path, runner=fake_runner)
    assert ok is True
    assert len(calls) == 2
    assert calls[0][0][1] == "install"
    assert calls[1][0][1] == "build"
    assert calls[0][1] == str(tmp_path / "web")


def test_build_web_app_fails(tmp_path):
    def fake_runner(cmd, **kwargs):
        if cmd[1] == "build":
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="build error")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    ok = setup.build_web_app(tmp_path, runner=fake_runner)
    assert ok is False


def test_register_mcp_server_already_registered(tmp_path):
    server_dir = tmp_path / "server"
    server_dir.mkdir()
    norm_path = str(server_dir.resolve()).replace("\\", "/")

    calls = []

    def fake_runner(cmd, **kwargs):
        calls.append(cmd)
        if "get" in cmd:
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=f"socra:\n  Args: run --project {norm_path} socra-server\n",
                stderr="",
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    ok = setup.register_mcp_server(server_dir, runner=fake_runner)
    assert ok is True
    # Should only run `claude mcp get socra`, not add
    assert len(calls) == 1
    assert "get" in calls[0]


def test_register_mcp_server_needs_update(tmp_path):
    server_dir = tmp_path / "server"
    server_dir.mkdir()

    calls = []

    def fake_runner(cmd, **kwargs):
        calls.append(cmd)
        if "get" in cmd:
            # Different path
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout="socra:\n  Args: run --project /other/path/server socra-server\n",
                stderr="",
            )
        if "remove" in cmd or "add" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="OK\n", stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")

    ok = setup.register_mcp_server(server_dir, runner=fake_runner)
    assert ok is True
    assert len(calls) == 3
    assert "get" in calls[0]
    assert "remove" in calls[1]
    assert "add" in calls[2]
    assert str(server_dir.resolve()) in calls[2]


def test_register_mcp_server_new_registration(tmp_path):
    server_dir = tmp_path / "server"
    server_dir.mkdir()

    calls = []

    def fake_runner(cmd, **kwargs):
        calls.append(cmd)
        if "get" in cmd:
            # Not found
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="No MCP server named socra")
        if "add" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="Added server socra\n", stderr="")
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="")

    ok = setup.register_mcp_server(server_dir, runner=fake_runner)
    assert ok is True
    assert len(calls) == 2
    assert "get" in calls[0]
    assert "add" in calls[1]
    assert str(server_dir.resolve()) in calls[1]


def test_predownload_models(monkeypatch):
    mock_hf = MagicMock()
    mock_whisper_download = MagicMock()

    import huggingface_hub
    import faster_whisper

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", mock_hf)
    monkeypatch.setattr(faster_whisper, "download_model", mock_whisper_download)

    ok = setup.predownload_models()
    assert ok is True
    assert mock_hf.call_count == 2
    assert mock_whisper_download.call_count == 1


def test_run_setup_aborts_on_failed_prerequisites(monkeypatch):
    def fake_check(runner):
        return [
            setup.PrerequisiteResult("uv", False, "", "Missing uv", "Install uv"),
        ]

    monkeypatch.setattr(setup, "check_prerequisites", fake_check)

    exit_code = setup.run_setup()
    assert exit_code == 1


def test_run_setup_success(monkeypatch, tmp_path):
    monkeypatch.setattr(setup, "get_repo_root", lambda: tmp_path)
    monkeypatch.setattr(setup, "check_prerequisites", lambda runner: [
        setup.PrerequisiteResult("uv", True, "0.5.0"),
        setup.PrerequisiteResult("node", True, "v22.0.0"),
        setup.PrerequisiteResult("pnpm", True, "9.0.0"),
        setup.PrerequisiteResult("claude", True, "1.0.0"),
    ])
    monkeypatch.setattr(setup, "build_web_app", lambda repo_root, runner: True)
    monkeypatch.setattr(setup, "register_mcp_server", lambda server_dir, runner: True)
    monkeypatch.setattr(setup, "predownload_models", lambda: True)

    exit_code = setup.run_setup(shortcut=False)
    assert exit_code == 0


def test_main_cli_dispatch(monkeypatch):
    monkeypatch.setattr(setup.sys, "argv", ["setup", "--skip-models", "--skip-web"])
    ran_flags = {}

    def fake_run_setup(shortcut, skip_models, skip_web):
        ran_flags["shortcut"] = shortcut
        ran_flags["skip_models"] = skip_models
        ran_flags["skip_web"] = skip_web
        return 0

    monkeypatch.setattr(setup, "run_setup", fake_run_setup)
    with pytest.raises(SystemExit) as exc_info:
        setup.main(["--skip-models", "--skip-web"])
    assert exc_info.value.code == 0
    assert ran_flags == {"shortcut": False, "skip_models": True, "skip_web": True}


def test_main_entrypoint_dispatches_setup(monkeypatch):
    from socra_server import __main__ as main_mod

    ran = []

    def fake_setup_main(args):
        ran.append(args)

    monkeypatch.setattr("socra_server.setup.main", fake_setup_main)
    monkeypatch.setattr(setup.sys, "argv", ["socra-server", "setup", "--shortcut"])

    main_mod.main()
    assert ran == [["--shortcut"]]
