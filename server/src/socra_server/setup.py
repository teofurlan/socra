"""One-command setup for Socra (Issue #93).

Checks prerequisites, builds the web application, registers the Claude Code MCP
server idempotently with the current absolute server path, pre-downloads speech
models, and optionally creates the desktop shortcut.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import NamedTuple

from socra_server.adapters.piper_tts import MODEL_REPO, _voice_stack_dir
from socra_server.adapters.whisper_stt import get_whisper_config
from socra_server.domain.speech import SPEECH_VOICE_ID
from socra_server.domain.voices import get_voice


class PrerequisiteResult(NamedTuple):
    name: str
    ok: bool
    version: str
    error_message: str | None = None
    install_guide: str | None = None


def get_repo_root() -> Path:
    """Resolve repository root relative to this module."""
    return Path(__file__).resolve().parents[3]


def check_prerequisites(runner=subprocess.run) -> list[PrerequisiteResult]:
    """Verify uv, node (>=22), pnpm, and claude CLI."""
    results: list[PrerequisiteResult] = []

    # 1. uv
    uv_bin = shutil.which("uv")
    if not uv_bin:
        results.append(
            PrerequisiteResult(
                name="uv",
                ok=False,
                version="",
                error_message="uv package manager not found in PATH.",
                install_guide="Install uv from https://docs.astral.sh/uv/getting-started/installation/",
            )
        )
    else:
        try:
            res = runner([uv_bin, "--version"], capture_output=True, text=True, check=False)
            ver = res.stdout.strip() if res.returncode == 0 else "unknown"
            results.append(PrerequisiteResult(name="uv", ok=True, version=ver))
        except Exception as exc:
            results.append(
                PrerequisiteResult(
                    name="uv",
                    ok=False,
                    version="",
                    error_message=str(exc),
                    install_guide="Reinstall uv: https://docs.astral.sh/uv/",
                )
            )

    # 2. node
    node_bin = shutil.which("node")
    if not node_bin:
        results.append(
            PrerequisiteResult(
                name="node",
                ok=False,
                version="",
                error_message="Node.js not found in PATH.",
                install_guide="Install Node.js 22+ from https://nodejs.org/",
            )
        )
    else:
        try:
            res = runner([node_bin, "--version"], capture_output=True, text=True, check=False)
            ver_str = res.stdout.strip().lstrip("v")
            major = int(ver_str.split(".")[0]) if ver_str and ver_str[0].isdigit() else 0
            if major >= 22:
                results.append(PrerequisiteResult(name="node", ok=True, version=f"v{ver_str}"))
            else:
                results.append(
                    PrerequisiteResult(
                        name="node",
                        ok=False,
                        version=f"v{ver_str}",
                        error_message=f"Node.js version {ver_str} is below required v22+.",
                        install_guide="Upgrade Node.js to v22+ from https://nodejs.org/",
                    )
                )
        except Exception as exc:
            results.append(
                PrerequisiteResult(
                    name="node",
                    ok=False,
                    version="",
                    error_message=str(exc),
                    install_guide="Install Node.js 22+ from https://nodejs.org/",
                )
            )

    # 3. pnpm
    pnpm_bin = shutil.which("pnpm")
    if not pnpm_bin:
        results.append(
            PrerequisiteResult(
                name="pnpm",
                ok=False,
                version="",
                error_message="pnpm not found in PATH.",
                install_guide="Install pnpm: https://pnpm.io/installation (or run 'corepack enable')",
            )
        )
    else:
        try:
            res = runner([pnpm_bin, "--version"], capture_output=True, text=True, check=False)
            ver = res.stdout.strip() if res.returncode == 0 else "unknown"
            results.append(PrerequisiteResult(name="pnpm", ok=True, version=ver))
        except Exception as exc:
            results.append(
                PrerequisiteResult(
                    name="pnpm",
                    ok=False,
                    version="",
                    error_message=str(exc),
                    install_guide="Install pnpm from https://pnpm.io/",
                )
            )

    # 4. claude CLI
    claude_bin = shutil.which("claude")
    if not claude_bin:
        results.append(
            PrerequisiteResult(
                name="claude",
                ok=False,
                version="",
                error_message="Claude Code CLI ('claude') not found in PATH.",
                install_guide="Install Claude Code: https://docs.claude.com/en/docs/claude-code",
            )
        )
    else:
        try:
            res = runner([claude_bin, "--version"], capture_output=True, text=True, check=False)
            ver = res.stdout.strip() if res.returncode == 0 else "unknown"
            results.append(PrerequisiteResult(name="claude", ok=True, version=ver))
        except Exception as exc:
            results.append(
                PrerequisiteResult(
                    name="claude",
                    ok=False,
                    version="",
                    error_message=str(exc),
                    install_guide="Install Claude Code: https://docs.claude.com/en/docs/claude-code",
                )
            )

    return results


def build_web_app(repo_root: Path, runner=subprocess.run) -> bool:
    """Run pnpm install and pnpm build inside web directory."""
    web_dir = repo_root / "web"
    pnpm_bin = shutil.which("pnpm") or "pnpm"

    print("Building web client (pnpm install & build)...")
    install_res = runner([pnpm_bin, "install"], cwd=str(web_dir), check=False)
    if install_res.returncode != 0:
        print("Error: 'pnpm install' failed in web directory.", file=sys.stderr)
        return False

    build_res = runner([pnpm_bin, "build"], cwd=str(web_dir), check=False)
    if build_res.returncode != 0:
        print("Error: 'pnpm build' failed in web directory.", file=sys.stderr)
        return False

    return True


def register_mcp_server(
    server_dir: Path,
    runner=subprocess.run,
) -> bool:
    """Register or update socra MCP server for Claude Code user scope idempotently."""
    claude_bin = shutil.which("claude") or "claude"
    server_path_str = str(server_dir.resolve()).replace("\\", "/")

    # Check existing configuration with `claude mcp get socra`
    get_res = runner(
        [claude_bin, "mcp", "get", "socra"],
        capture_output=True,
        text=True,
        check=False,
    )

    if get_res.returncode == 0:
        # Check if the path matches
        output = get_res.stdout
        # Normalize backslashes for path comparison
        norm_output = output.replace("\\", "/").lower()
        norm_target = server_path_str.lower()
        if norm_target in norm_output:
            print("Claude Code MCP server 'socra' is already registered with current path.")
            return True
        print(f"Updating Claude Code MCP server 'socra' registration to {server_path_str}...")
        # claude mcp add fails if server exists; remove old user registration first
        runner([claude_bin, "mcp", "remove", "--scope", "user", "socra"], check=False)
    else:
        print(f"Registering Claude Code MCP server 'socra' ({server_path_str})...")

    # `claude mcp add --scope user socra -- uv run --project "<server_path>" socra-server`
    add_cmd = [
        claude_bin,
        "mcp",
        "add",
        "--scope",
        "user",
        "socra",
        "--",
        "uv",
        "run",
        "--project",
        str(server_dir.resolve()),
        "socra-server",
    ]
    add_res = runner(add_cmd, check=False)
    if add_res.returncode != 0:
        print("Error: failed to register MCP server with claude CLI.", file=sys.stderr)
        return False

    return True


def predownload_models() -> bool:
    """Download default Piper voice and Whisper model files if not present."""
    print("Pre-downloading speech models...")

    # 1. Piper voice
    voice = get_voice(SPEECH_VOICE_ID)
    if not voice:
        print(f"Warning: Default voice '{SPEECH_VOICE_ID}' not found in catalogue.", file=sys.stderr)
    else:
        try:
            print(f"Checking / downloading Piper TTS voice ({voice.label} - {voice.model})...")
            from huggingface_hub import hf_hub_download

            hf_hub_download(MODEL_REPO, f"{voice.model}.onnx")
            hf_hub_download(MODEL_REPO, f"{voice.model}.onnx.json")
            print("Piper TTS voice files are ready.")
        except Exception as exc:
            print(f"Error downloading Piper voice: {exc}", file=sys.stderr)
            return False

    # 2. Whisper model
    model_size, device, compute_type = get_whisper_config()
    print(f"Checking / downloading Whisper STT model ({model_size})...")
    try:
        from faster_whisper import download_model
        download_root = _voice_stack_dir() / "models" / "whisper"
        download_root.mkdir(parents=True, exist_ok=True)
        # faster_whisper.download_model fetches the model snapshot
        download_model(model_size, output_dir=str(download_root))
        print("Whisper STT model files are ready.")
    except Exception as exc:
        print(f"Error downloading Whisper model: {exc}", file=sys.stderr)
        return False

    return True


def install_desktop_shortcut(server_dir: Path, runner=subprocess.run) -> bool:
    """Run server/install-shortcut.ps1 on Windows."""
    if sys.platform != "win32":
        print("Desktop shortcut is only supported on Windows.")
        return True

    ps_script = server_dir / "install-shortcut.ps1"
    if not ps_script.exists():
        print(f"Warning: {ps_script} not found.", file=sys.stderr)
        return False

    print("Creating desktop shortcut for Socra...")
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(ps_script),
    ]
    res = runner(cmd, check=False)
    return res.returncode == 0


def run_setup(
    shortcut: bool = False,
    skip_models: bool = False,
    skip_web: bool = False,
    runner=subprocess.run,
) -> int:
    """Run full setup workflow."""
    repo_root = get_repo_root()
    server_dir = repo_root / "server"

    print("=" * 60)
    print("Socra Setup: preparing your environment")
    print("=" * 60)

    # 1. Prerequisites
    prereqs = check_prerequisites(runner=runner)
    failed_prereqs = [p for p in prereqs if not p.ok]
    for p in prereqs:
        if p.ok:
            print(f"  [OK] {p.name} ({p.version})")
        else:
            print(f"  [FAIL] {p.name}: {p.error_message}")
            if p.install_guide:
                print(f"         -> {p.install_guide}")

    if failed_prereqs:
        print("\nSetup aborted: missing required prerequisites. Please install them and rerun setup.", file=sys.stderr)
        return 1

    # 2. Build web client
    if not skip_web:
        if not build_web_app(repo_root, runner=runner):
            return 1
    else:
        print("Skipping web client build (--skip-web).")

    # 3. Register MCP server
    if not register_mcp_server(server_dir, runner=runner):
        return 1

    # 4. Pre-download models
    if not skip_models:
        if not predownload_models():
            return 1
    else:
        print("Skipping model downloads (--skip-models).")

    # 5. Desktop shortcut (optional or Windows default)
    if shortcut:
        install_desktop_shortcut(server_dir, runner=runner)

    print("\n" + "=" * 60)
    print("Socra is ready!")
    print("  - Exam mode: ask Claude Code to examine you on any project.")
    print("  - Agent mode: uv run --project server socra-server --agent")
    if sys.platform == "win32" and not shortcut:
        print("  - Tip: run with --shortcut to install the desktop icon.")
    print("=" * 60)
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Socra one-command setup")
    parser.add_argument("--shortcut", action="store_true", help="Create desktop shortcut (Windows)")
    parser.add_argument("--skip-models", action="store_true", help="Skip pre-downloading Piper/Whisper models")
    parser.add_argument("--skip-web", action="store_true", help="Skip web client build")
    args = parser.parse_args(argv)

    code = run_setup(
        shortcut=args.shortcut,
        skip_models=args.skip_models,
        skip_web=args.skip_web,
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
