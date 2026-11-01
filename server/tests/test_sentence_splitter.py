"""Tests for the incremental sentence splitter that feeds sentence-by-sentence speech."""
from __future__ import annotations

from socra_server.domain.sentences import SentenceSplitter, split_sentences


def _stream(chunks: list[str]) -> list[str]:
    splitter = SentenceSplitter()
    out: list[str] = []
    for chunk in chunks:
        out.extend(splitter.feed(chunk))
    out.extend(splitter.flush())
    return out


def test_a_sentence_is_released_only_once_it_is_complete():
    splitter = SentenceSplitter()

    assert splitter.feed("Voy a verificarlo") == []
    assert splitter.feed(" en la memoria.") == []  # may still be "memoria.txt"
    assert splitter.feed(" Ahora") == ["Voy a verificarlo en la memoria."]
    assert splitter.flush() == ["Ahora"]


def test_question_and_exclamation_marks_end_sentences():
    assert split_sentences("Really? Yes! Done.") == ["Really?", "Yes!", "Done."]


def test_chunk_boundaries_do_not_change_the_result():
    text = "First one. Second one! Third one? Fourth."
    expected = split_sentences(text)

    assert _stream(list(text)) == expected
    assert _stream([text[:7], text[7:20], text[20:]]) == expected


def test_decimals_and_dotted_names_do_not_split():
    assert split_sentences("Version 3.5 is out. See os.path.join for it.") == [
        "Version 3.5 is out.", "See os.path.join for it.",
    ]


def test_common_abbreviations_do_not_split():
    assert split_sentences("Ask Dr. Smith about it, e.g. today. Then go.") == [
        "Ask Dr. Smith about it, e.g. today.", "Then go.",
    ]


def test_etc_splits_only_when_a_new_sentence_follows():
    assert split_sentences("Files, dirs, etc. are listed. Next, etc. Then more.") == [
        "Files, dirs, etc. are listed.", "Next, etc.", "Then more.",
    ]


def test_initials_do_not_split():
    assert split_sentences("Written by J. Smith today. Next.") == [
        "Written by J. Smith today.", "Next.",
    ]


def test_ellipsis_splits_only_before_a_capital():
    assert split_sentences("Well... maybe so. Hmm... Okay then.") == [
        "Well... maybe so.", "Hmm...", "Okay then.",
    ]
    assert split_sentences("Wait… Yes.") == ["Wait…", "Yes."]


def test_closing_quotes_and_emphasis_stay_with_their_sentence():
    assert split_sentences('He said "stop." Then left. **Done.** Next.') == [
        'He said "stop."', "Then left.", "**Done.**", "Next.",
    ]


def test_blank_lines_separate_pieces_without_punctuation():
    assert split_sentences("## Title\n\nSome text without a stop\n\nEnd.") == [
        "## Title", "Some text without a stop", "End.",
    ]


def test_list_items_are_separate_pieces_and_numbers_are_not_sentences():
    text = "Steps:\n1. First thing\n2. Second thing\n- bullet"

    assert split_sentences(text) == ["Steps:", "1. First thing", "2. Second thing", "- bullet"]


def test_text_before_a_code_fence_is_released_without_waiting_for_the_fence():
    splitter = SentenceSplitter()

    assert splitter.feed("Run this:\n```py\nprint('a. b')\n") == ["Run this:"]
    assert splitter.feed("x = 1.\n") == []  # still inside the fence
    assert splitter.feed("```\nThen check it. ") == ["```py\nprint('a. b')\nx = 1.\n```", "Then check it."]


def test_periods_inside_a_fenced_block_never_split_it():
    text = "Intro.\n```\nfirst. second. third.\n```\nOutro."

    assert split_sentences(text) == ["Intro.", "```\nfirst. second. third.\n```", "Outro."]


def test_tilde_fences_are_respected_and_an_unclosed_fence_is_flushed_whole():
    splitter = SentenceSplitter()

    assert splitter.feed("~~~\na. b. c.") == []
    assert splitter.flush() == ["~~~\na. b. c."]


def test_flush_empties_the_splitter_and_ignores_whitespace():
    splitter = SentenceSplitter()
    splitter.feed("Done. ")

    assert splitter.flush() == []
    assert splitter.feed("Again. ") == ["Again."]
