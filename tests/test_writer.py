"""Tests for Writer Agent."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.schemas import NewsArticle
from src.writer_agent import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    WriterAgent,
)


class TestWriterAgent:
    def test_writer_requires_api_key(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="GEMINI_API_KEY"):
                WriterAgent()

    def test_default_model_and_temperature(self) -> None:
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            with patch("src.writer_agent.ChatGoogleGenerativeAI") as mock_gemini:
                WriterAgent()
                mock_gemini.assert_called_once_with(
                    model=DEFAULT_MODEL,
                    google_api_key="test-key",
                    temperature=DEFAULT_TEMPERATURE,
                    max_output_tokens=DEFAULT_MAX_TOKENS,
                    thinking_level="low",
                )

    def test_create_system_prompt(self) -> None:
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            with patch("src.writer_agent.ChatGoogleGenerativeAI"):
                agent = WriterAgent()
                prompt = agent.create_system_prompt()
                assert "Top Headlines" in prompt
                assert "ELITE AI NEWSLETTER WRITER" in prompt
                assert "RETURN ONLY THE FINAL NEWSLETTER" in prompt

    def test_prepare_articles_for_prompt(self, sample_articles: list[NewsArticle]) -> None:
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            with patch("src.writer_agent.ChatGoogleGenerativeAI"):
                agent = WriterAgent()
                json_str = agent.prepare_articles_for_prompt(sample_articles)
                data = json.loads(json_str)

                assert len(data) == min(len(sample_articles), 12)
                assert data[0]["t"]
                assert "u" in data[0]
                assert "score" in data[0]
                assert "src" in data[0]

    def test_format_as_markdown_strips_fences(self) -> None:
        raw = "```markdown\n# AI News\n\nContent here.\n```"
        result = WriterAgent.format_as_markdown(raw)
        assert result.startswith("# AI News")
        assert "```" not in result

    def test_format_as_markdown_adds_heading(self) -> None:
        result = WriterAgent.format_as_markdown("Some content without heading.")
        assert result.startswith("# AI News Newsletter")

    def test_call_llm(self) -> None:
        mock_response = MagicMock()
        mock_response.content = "# Newsletter"

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            with patch("src.writer_agent.ChatGoogleGenerativeAI") as mock_gemini:
                mock_llm = MagicMock()
                mock_llm.invoke = MagicMock(return_value=mock_response)
                mock_gemini.return_value = mock_llm

                agent = WriterAgent()
                response = agent.call_llm("system", "user")

                mock_llm.invoke.assert_called_once()
                assert response.content == "# Newsletter"

    def test_write_newsletter(self, sample_articles: list[NewsArticle]) -> None:
        mock_response = MagicMock()
        mock_response.content = "# AI News Newsletter\n\n## Top Headlines\n\nTest content."

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            with patch("src.writer_agent.ChatGoogleGenerativeAI") as mock_gemini:
                mock_llm = MagicMock()
                mock_llm.invoke = MagicMock(return_value=mock_response)
                mock_gemini.return_value = mock_llm

                agent = WriterAgent()
                newsletter = agent.write_newsletter(sample_articles)

        assert newsletter.startswith("# AI News Newsletter")
        assert "Top Headlines" in newsletter
        mock_llm.invoke.assert_called_once()

    def test_build_budgeted_prompts_within_limit(
        self,
        sample_articles: list[NewsArticle],
    ) -> None:
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            with patch("src.writer_agent.ChatGoogleGenerativeAI"):
                agent = WriterAgent(max_input_tokens=32000)
                _, user_prompt, meta = agent._build_budgeted_prompts(
                    sample_articles * 5
                )

        assert meta["within_budget"] is True
        assert meta["estimated_input_tokens"] <= 32000
        assert len(user_prompt) > 0

    def test_write_newsletter_empty_llm_uses_fallback(
        self,
        sample_articles: list[NewsArticle],
    ) -> None:
        mock_response = MagicMock()
        mock_response.content = ""

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            with patch("src.writer_agent.ChatGoogleGenerativeAI") as mock_gemini:
                mock_llm = MagicMock()
                mock_llm.invoke = MagicMock(return_value=mock_response)
                mock_gemini.return_value = mock_llm

                agent = WriterAgent()
                newsletter = agent.write_newsletter(sample_articles)

        assert len(newsletter) > 100
        assert "AI News" in newsletter
        mock_llm.invoke.assert_called_once()

    def test_write_newsletter_empty_articles(self) -> None:
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            with patch("src.writer_agent.ChatGoogleGenerativeAI"):
                agent = WriterAgent()
                newsletter = agent.write_newsletter([])

        assert newsletter.startswith("# AI News Newsletter")
        assert "No articles available" in newsletter

    @pytest.mark.asyncio
    async def test_write_async(self, sample_articles: list[NewsArticle]) -> None:
        mock_response = MagicMock()
        mock_response.content = "# AI Daily Digest\n\n## Top Headlines\n\nTest newsletter content."

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            with patch("src.writer_agent.ChatGoogleGenerativeAI") as mock_gemini:
                mock_llm = AsyncMock()
                mock_llm.ainvoke = AsyncMock(return_value=mock_response)
                mock_gemini.return_value = mock_llm

                agent = WriterAgent()
                newsletter = await agent.write(sample_articles)

        assert "AI Daily Digest" in newsletter
        assert len(newsletter) > 0
        mock_llm.ainvoke.assert_called_once()
