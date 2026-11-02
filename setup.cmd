@echo off
setlocal
cd /d "%~dp0"
uv run --project server socra-server setup %*
