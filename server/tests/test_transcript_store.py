"""Tests for the Socra-owned session transcripts."""
from __future__ import annotations

import json
import os
import time

from socra_server.adapters.transcript_store import RETENTION_DAYS, TranscriptStore


def test_appended_turns_are_written_as_jsonl_under_a_project_folder(tmp_path):
    store = TranscriptStore(tmp_path / "sessions")
    transcript = store.start(tmp_path / "project")

    transcript.append("user", "Add a login page")
    transcript.append("agent", "Done, it lives in login.tsx")

    files = list((tmp_path / "sessions").glob("*/*.jsonl"))
    assert [f.stem for f in files] == [transcript.session_id]
    lines = [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]
    assert [(l["role"], l["text"]) for l in lines] == [
        ("user", "Add a login page"), ("agent", "Done, it lives in login.tsx"),
    ]


def test_same_project_shares_a_folder_and_different_projects_do_not(tmp_path):
    store = TranscriptStore(tmp_path / "sessions")
    first = store.start(tmp_path / "a")
    second = store.start(tmp_path / "a")
    other = store.start(tmp_path / "b")
    for t in (first, second, other):
        t.append("user", "hi")

    folders = {p.parent for p in (tmp_path / "sessions").glob("*/*.jsonl")}
    assert len(folders) == 2
    assert first.session_id != second.session_id


def test_search_finds_matches_case_insensitively_with_a_snippet(tmp_path):
    transcript = TranscriptStore(tmp_path).start(tmp_path / "p")
    transcript.append("user", "Which token store did we pick?")
    transcript.append("agent", "We chose the OS keychain for the Refresh Token.")
    transcript.append("user", "unrelated")

    hits = transcript.search("refresh token")

    assert [(h.turn, h.role) for h in hits] == [(2, "agent")]
    assert "OS keychain" in hits[0].snippet


def test_search_honours_the_limit_and_handles_a_blank_query(tmp_path):
    transcript = TranscriptStore(tmp_path).start(tmp_path / "p")
    for i in range(5):
        transcript.append("user", f"note {i}")

    assert len(transcript.search("note", limit=2)) == 2
    assert transcript.search("  ") == []


def test_search_without_any_turns_returns_nothing(tmp_path):
    assert TranscriptStore(tmp_path).start(tmp_path / "p").search("x") == []


def test_prune_removes_only_sessions_older_than_the_retention(tmp_path):
    now = time.time()
    store = TranscriptStore(tmp_path, now=lambda: now)
    old = store.start(tmp_path / "p")
    old.append("user", "old")
    fresh = store.start(tmp_path / "p")
    fresh.append("user", "fresh")
    stale = now - (RETENTION_DAYS + 1) * 86400
    os.utime(old.path, (stale, stale))

    removed = store.prune()

    assert removed == 1
    assert not old.path.exists()
    assert fresh.path.exists()


def test_prune_drops_empty_project_folders_and_tolerates_a_missing_root(tmp_path):
    now = time.time()
    store = TranscriptStore(tmp_path / "none", now=lambda: now)
    assert store.prune() == 0
    store = TranscriptStore(tmp_path / "s", now=lambda: now)
    only = store.start(tmp_path / "p")
    only.append("user", "x")
    stale = now - (RETENTION_DAYS + 1) * 86400
    os.utime(only.path, (stale, stale))

    store.prune()

    assert list((tmp_path / "s").iterdir()) == []


def test_unencodable_text_and_corrupt_bytes_never_break_append_or_search(tmp_path):
    transcript = TranscriptStore(tmp_path).start(tmp_path / "p")
    transcript.append("user", "lone surrogate \ud800 here")
    transcript.append("user", "needle after")
    with transcript.path.open("ab") as handle:
        handle.write(b"\xff\xfe broken\n")

    assert [h.turn for h in transcript.search("needle")] == [1]


def test_write_failures_never_raise_into_the_conversation(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("not a folder")
    transcript = TranscriptStore(blocker).start(tmp_path / "p")

    transcript.append("user", "still fine")

    assert transcript.search("still") == []
