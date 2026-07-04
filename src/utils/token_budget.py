"""Token estimation and prompt budgeting for writer LLM input limits."""

from __future__ import annotations

import json
import os
from typing import Any, Callable

DEFAULT_WRITER_MAX_INPUT_TOKENS = int(
    os.getenv(
        "WRITER_MAX_INPUT_TOKENS",
        os.getenv("GEMINI_MAX_INPUT_TOKENS", os.getenv("GROQ_MAX_INPUT_TOKENS", "32000")),
    )
)
# Backward-compatible alias
DEFAULT_GROQ_MAX_INPUT_TOKENS = DEFAULT_WRITER_MAX_INPUT_TOKENS
PROMPT_OVERHEAD_TOKENS = 64


def estimate_tokens(text: str) -> int:
    """Conservative token estimate without external tokenizers."""
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


def estimate_messages_tokens(system_prompt: str, user_prompt: str) -> int:
    return (
        estimate_tokens(system_prompt)
        + estimate_tokens(user_prompt)
        + PROMPT_OVERHEAD_TOKENS
    )


def fit_user_prompt_to_budget(
    *,
    system_prompt: str,
    date_str: str,
    article_payloads: list[list[dict[str, Any]]],
    format_user_prompt: Callable[[list[dict[str, Any]], str], str],
    max_input_tokens: int,
) -> tuple[str, dict[str, Any]]:
    """Pick the largest article payload that fits within the token budget."""
    metadata: dict[str, Any] = {
        "max_input_tokens": max_input_tokens,
        "system_tokens": estimate_tokens(system_prompt),
        "selected_articles": 0,
        "summary_chars": 0,
        "estimated_input_tokens": 0,
        "within_budget": False,
    }

    if not article_payloads:
        user_prompt = format_user_prompt([], date_str)
        metadata["estimated_input_tokens"] = estimate_messages_tokens(
            system_prompt, user_prompt
        )
        metadata["within_budget"] = (
            metadata["estimated_input_tokens"] <= max_input_tokens
        )
        return user_prompt, metadata

    for payload in article_payloads:
        user_prompt = format_user_prompt(payload, date_str)
        total = estimate_messages_tokens(system_prompt, user_prompt)
        metadata["estimated_input_tokens"] = total
        metadata["selected_articles"] = len(payload)
        if payload:
            first_summary = payload[0].get("s", "")
            metadata["summary_chars"] = len(first_summary)

        if total <= max_input_tokens:
            metadata["within_budget"] = True
            return user_prompt, metadata

    # Smallest payload still too large — return it and let caller handle fallback.
    smallest = article_payloads[-1]
    user_prompt = format_user_prompt(smallest, date_str)
    metadata["selected_articles"] = len(smallest)
    metadata["estimated_input_tokens"] = estimate_messages_tokens(
        system_prompt, user_prompt
    )
    metadata["within_budget"] = False
    return user_prompt, metadata


def dumps_compact_json(data: Any) -> str:
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False, default=str)
