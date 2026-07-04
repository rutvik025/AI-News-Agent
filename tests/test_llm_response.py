"""Tests for LLM response text extraction."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.utils.llm_response import extract_llm_text


def test_extract_llm_text_from_string() -> None:
    response = MagicMock()
    response.content = "# Newsletter\n\nBody"
    assert extract_llm_text(response) == "# Newsletter\n\nBody"


def test_extract_llm_text_from_block_list() -> None:
    response = MagicMock()
    response.content = [{"type": "text", "text": "Hello world"}]
    assert extract_llm_text(response) == "Hello world"


def test_extract_llm_text_empty() -> None:
    response = MagicMock()
    response.content = ""
    response.additional_kwargs = {}
    response.response_metadata = {}
    assert extract_llm_text(response) == ""
