"""Tests for token budgeting utilities."""

from __future__ import annotations

from src.utils.token_budget import (
    estimate_messages_tokens,
    estimate_tokens,
    fit_user_prompt_to_budget,
)


def _format_user(articles: list[dict], date_str: str) -> str:
    return f"date={date_str}|articles={len(articles)}"


class TestTokenBudget:
    def test_estimate_tokens_nonempty(self) -> None:
        assert estimate_tokens("abcd") == 1
        assert estimate_tokens("a" * 100) == 25

    def test_fit_user_prompt_to_budget_selects_largest_fit(self) -> None:
        system_prompt = "system"
        payloads = [
            [{"t": "x" * 5000}],
            [{"t": "x" * 100}],
        ]
        user_prompt, meta = fit_user_prompt_to_budget(
            system_prompt=system_prompt,
            date_str="2026-06-25",
            article_payloads=payloads,
            format_user_prompt=_format_user,
            max_input_tokens=estimate_messages_tokens(system_prompt, _format_user(payloads[1], "2026-06-25")),
        )
        assert user_prompt == _format_user(payloads[1], "2026-06-25")
        assert meta["within_budget"] is True
        assert meta["selected_articles"] == 1
