"""Socra's log file: set up by the running server, never by importing it (#89)."""
from __future__ import annotations

import logging
import logging.handlers

from socra_server.entrypoints import ws_server


def _file_handlers(name: str) -> list[logging.Handler]:
    return [
        h for h in logging.getLogger(name).handlers
        if isinstance(h, logging.handlers.RotatingFileHandler)
    ]


def test_importing_the_server_writes_no_log_file():
    # Tests import the server: they must not write into the developer's real log.
    assert _file_handlers("socra_server") == []
    assert _file_handlers("socra_server.entrypoints.ws_server") == []


def test_the_log_file_records_the_agent_flow_not_only_the_websocket(tmp_path):
    path = tmp_path / "logs" / "socra.log"
    handler = ws_server.setup_file_logging(path)
    try:
        logging.getLogger("socra_server.agent_app").info("Mode switch to exam: started")
        logging.getLogger("socra_server.entrypoints.ws_server").info("Agent page connected")
        logging.getLogger("httpx").info("not Socra")
        handler.flush()
        text = path.read_text(encoding="utf-8")
    finally:
        logging.getLogger("socra_server").removeHandler(handler)
        handler.close()

    assert "[INFO] socra_server.agent_app: Mode switch to exam: started" in text
    assert "socra_server.entrypoints.ws_server: Agent page connected" in text
    assert "not Socra" not in text


def test_setting_up_twice_keeps_one_file_handler(tmp_path):
    path = tmp_path / "socra.log"
    first = ws_server.setup_file_logging(path)
    try:
        second = ws_server.setup_file_logging(path)
        assert second is first
        assert len(_file_handlers("socra_server")) == 1
    finally:
        logging.getLogger("socra_server").removeHandler(first)
        first.close()


def test_socra_log_file_moves_the_log(tmp_path, monkeypatch):
    monkeypatch.setenv("SOCRA_LOG_FILE", str(tmp_path / "other.log"))
    assert ws_server.log_path() == tmp_path / "other.log"


def test_the_log_stays_in_server_logs_by_default(monkeypatch):
    monkeypatch.delenv("SOCRA_LOG_FILE", raising=False)
    assert ws_server.log_path() == ws_server.LOG_PATH
    assert ws_server.LOG_PATH.parts[-2:] == ("logs", "socra.log")
