"""Tests for the pronunciation glossary: loading and segmentation."""
from __future__ import annotations

import json

import pytest

from socra_server.domain import glossary
from socra_server.domain.glossary import DEFAULT_TERMS, load_glossary



def test_load_glossary_reads_terms(tmp_path):
    path = tmp_path / "terms.json"
    path.write_text(json.dumps({"version": 1, "terms": {"hook": "hook"}}), encoding="utf-8")
    assert load_glossary(path) == {"hook": "hook"}


def test_missing_file_falls_back_to_defaults(tmp_path):
    assert load_glossary(tmp_path / "absent.json") == DEFAULT_TERMS
    assert load_glossary(None) == DEFAULT_TERMS


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "[]",
        json.dumps({"version": 2, "terms": {"a": "b"}}),
        json.dumps({"version": 1}),
        json.dumps({"version": 1, "terms": {"": "b"}}),
        json.dumps({"version": 1, "terms": {"a": ""}}),
    ],
)
def test_invalid_file_is_rejected(tmp_path, content):
    path = tmp_path / "terms.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        load_glossary(path)
