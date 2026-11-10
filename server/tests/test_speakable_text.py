"""Tests for turning an agent's Markdown reply into text worth speaking."""
from __future__ import annotations

from socra_server.domain.speakable import SpokenPaths, speakable_text


def test_fenced_code_blocks_are_not_spoken():
    reply = "Run this:\n```python\nprint('hi')\n```\nThen check the output."

    assert speakable_text(reply) == "Run this: Then check the output."


def test_inline_code_keeps_its_text_without_backticks():
    assert speakable_text("Call `load()` first.") == "Call load() first."


def test_links_keep_only_their_label():
    assert speakable_text("See [the docs](https://example.com/x).") == "See the docs."


def test_headings_bullets_and_emphasis_markers_are_dropped():
    reply = "## Summary\n- **First** point\n* _second_ point\n1. third"

    assert speakable_text(reply) == "Summary First point second point third"


def test_composed_block_markers_are_all_dropped():
    reply = "> - **Quoted bullet**\n> 1. quoted step"

    assert speakable_text(reply) == "Quoted bullet quoted step"


def test_reply_with_only_code_has_nothing_to_speak():
    assert speakable_text("```\nls -la\n```") == ""


def test_plain_text_is_unchanged_apart_from_whitespace():
    assert speakable_text("  Hello,\n\nworld.  ") == "Hello, world."


def test_markers_inside_words_and_math_survive():
    assert speakable_text("Edit __init__ and compute 2**10.") == "Edit __init__ and compute 2**10."


def test_tilde_fences_are_not_spoken():
    assert speakable_text("Before\n~~~\ncode\n~~~\nafter") == "Before after"


def test_a_year_starting_a_line_is_not_a_list_number():
    assert speakable_text("2024. was a good year") == "2024. was a good year"


# Paths, URLs and commit hashes (#94): the page shows them in full, speech skips the noise.


def test_a_path_is_spoken_by_its_file_name_only():
    assert speakable_text("Edité `server/src/socra_server/app.py`.") == "Edité app."


def test_bare_paths_in_prose_are_spoken_by_their_file_name():
    assert speakable_text("Look at web/src/App.tsx and hooks/register.tsx.") == "Look at App and register."


def test_windows_and_relative_paths_follow_the_same_rule():
    reply = r"Open C:\Users\me\project\main.py, then ./scripts/run.sh and ../docs/notes.md."

    assert speakable_text(reply) == "Open main, then run and notes."


def test_a_directory_path_is_spoken_by_its_last_folder():
    assert speakable_text("Everything lives in `web/src/`.") == "Everything lives in src."


def test_a_file_name_shared_by_two_paths_keeps_its_folder():
    reply = "Edité `server/app.py` y `web/app.py`."

    assert speakable_text(reply) == "Edité server app y web app."


def test_the_same_path_twice_is_not_a_clash():
    assert speakable_text("See web/app.py, then fix web/app.py.") == "See app, then fix app."


def test_a_clash_with_an_earlier_piece_of_the_same_reply_keeps_the_folder():
    paths = SpokenPaths()

    first = speakable_text("Edité `server/app.py`.", paths)
    second = speakable_text("Ahora `web/app.py`.", paths)

    assert (first, second) == ("Edité app.", "Ahora web app.")


def test_pieces_of_different_replies_do_not_clash():
    assert speakable_text("Edité `server/app.py`.", SpokenPaths()) == "Edité app."
    assert speakable_text("Ahora `web/app.py`.", SpokenPaths()) == "Ahora app."


def test_a_commit_hash_is_not_spoken():
    reply = "Fixed in 93d470c and in 67e8037a5b2c9d1e0f4a6b8c7d9e1f2a3b4c5d6e."

    assert speakable_text(reply) == "Fixed in and in."


def test_a_url_is_spoken_as_its_site_name():
    reply = "See https://github.com/teofurlan/socra/pull/83, or www.python.org/downloads."

    assert speakable_text(reply) == "See github, or python."


def test_a_url_without_a_scheme_is_spoken_as_its_site_name():
    assert speakable_text("Open `github.com/teofurlan/socra/pull/83`.") == "Open github."


def test_a_url_keeps_the_site_name_past_subdomains_and_country_codes():
    reply = "Read https://docs.python.org/3/ and <https://www.bbc.co.uk/news>."

    assert speakable_text(reply) == "Read python and bbc."


def test_identifiers_numbers_versions_and_slashed_words_stay_unchanged():
    reply = (
        "Rename snake_case in __init__, keep Python 3.12 and v1.2.3, "
        "use Node.js and/or TCP/IP, 1/2 cup, 10/11/2026, 1234567 rows, decade, effaced."
    )

    assert speakable_text(reply) == reply
