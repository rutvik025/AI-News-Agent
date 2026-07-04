"""Writer Agent — generates newsletter using Gemini LLM.

This is the ONLY agent that uses an LLM and system prompt.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

# Groq (disabled — kept for reference)
# from langchain_groq import ChatGroq

from src.prompts.writer_prompt import WRITER_SYSTEM_PROMPT, format_writer_user_prompt
from src.schemas import NewsArticle
from src.utils.llm_response import extract_llm_text, extract_usage_metadata
from src.utils.logger import get_logger
from src.utils.timezone_utils import local_datetime_str
from src.utils.token_budget import (
    DEFAULT_WRITER_MAX_INPUT_TOKENS,
    estimate_messages_tokens,
    fit_user_prompt_to_budget,
)

logger = get_logger(__name__)

DEFAULT_MODEL = "gemini-3.5-flash"
DEFAULT_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.0-flash")
LLM_MAX_RETRIES = int(os.getenv("GEMINI_MAX_RETRIES", "4"))
LLM_RETRY_BASE_SECONDS = float(os.getenv("GEMINI_RETRY_BASE_SECONDS", "2.0"))
DEFAULT_TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "0.3"))
DEFAULT_MAX_TOKENS = int(
    os.getenv(
        "GEMINI_MAX_OUTPUT_TOKENS",
        os.getenv("GROQ_MAX_OUTPUT_TOKENS", "8192"),
    )
)
DEFAULT_MAX_ARTICLES = int(os.getenv("WRITER_MAX_ARTICLES", "12"))
MAX_SUMMARY_CHARS = int(os.getenv("WRITER_MAX_SUMMARY_CHARS", "280"))
WRITER_MAX_INPUT_TOKENS = int(
    os.getenv(
        "WRITER_MAX_INPUT_TOKENS",
        os.getenv(
            "GEMINI_MAX_INPUT_TOKENS",
            str(DEFAULT_WRITER_MAX_INPUT_TOKENS),
        ),
    )
)
SUMMARY_CHAR_STEPS = tuple(
    int(value)
    for value in os.getenv("WRITER_SUMMARY_CHAR_STEPS", "280,200,140,100,80").split(",")
    if value.strip()
)

# Groq defaults (disabled)
# GROQ_DEFAULT_MODEL = "openai/gpt-oss-120b"


class WriterAgent:
    """Generate professional markdown newsletter from ranked articles using Gemini."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_input_tokens: int = WRITER_MAX_INPUT_TOKENS,
    ) -> None:
        self.api_key = (
            api_key
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
            or ""
        )
        if not self.api_key:
            raise ValueError(
                "GEMINI_API_KEY (or GOOGLE_API_KEY) is required for WriterAgent"
            )

        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
        self.temperature = temperature
        self.max_input_tokens = max_input_tokens
        self.max_tokens = max_tokens
        self.provider = "gemini"
        self.llm = self._build_llm(self.model, temperature, max_tokens)

        # --- Groq setup (disabled) ---
        # self.api_key = api_key or os.getenv("GROQ_API_KEY", "")
        # if not self.api_key:
        #     raise ValueError("GROQ_API_KEY is required for WriterAgent")
        # self.model = model or os.getenv("GROQ_MODEL", GROQ_DEFAULT_MODEL)
        # groq_kwargs: dict[str, Any] = {
        #     "api_key": self.api_key,
        #     "model": self.model,
        #     "temperature": temperature,
        #     "max_tokens": max_tokens,
        # }
        # if "gpt-oss" in self.model or "openai/" in self.model:
        #     groq_kwargs["reasoning_effort"] = os.getenv("GROQ_REASONING_EFFORT", "low")
        # self.llm = ChatGroq(**groq_kwargs)
        # self.provider = "groq"

    def _build_llm(
        self,
        model_name: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatGoogleGenerativeAI:
        gemini_kwargs: dict[str, Any] = {
            "model": model_name,
            "google_api_key": self.api_key,
            "temperature": temperature if temperature is not None else self.temperature,
            "max_output_tokens": max_tokens if max_tokens is not None else self.max_tokens,
        }
        if model_name.startswith("gemini-3"):
            gemini_kwargs["thinking_level"] = os.getenv("GEMINI_THINKING_LEVEL", "low")
        return ChatGoogleGenerativeAI(**gemini_kwargs)

    @staticmethod
    def _is_transient_llm_error(exc: Exception) -> bool:
        message = str(exc).lower()
        markers = (
            "503",
            "429",
            "unavailable",
            "resource_exhausted",
            "high demand",
            "overloaded",
        )
        return any(marker in message for marker in markers)

    def create_system_prompt(self) -> str:
        """Return the system prompt for newsletter generation."""
        return WRITER_SYSTEM_PROMPT

    @staticmethod
    def _article_payload(
        article: NewsArticle,
        *,
        summary_chars: int,
        title_chars: int = 160,
    ) -> dict[str, Any]:
        return {
            "t": article.title[:title_chars],
            "u": article.link,
            "s": (article.summary or "")[:summary_chars],
            "src": (article.source or "")[:48],
            "score": round(article.importance_score or 0.0, 2),
        }

    def _candidate_payloads(
        self,
        articles: list[NewsArticle],
    ) -> list[list[dict[str, Any]]]:
        """Build progressively smaller article payloads for token budgeting."""
        ranked = articles[:DEFAULT_MAX_ARTICLES]
        candidates: list[list[dict[str, Any]]] = []

        for summary_chars in SUMMARY_CHAR_STEPS:
            for count in range(len(ranked), 0, -1):
                payload = [
                    self._article_payload(article, summary_chars=summary_chars)
                    for article in ranked[:count]
                ]
                candidates.append(payload)

        return candidates

    def prepare_articles_for_prompt(
        self,
        articles: list[NewsArticle],
        *,
        summary_chars: int | None = None,
        max_articles: int | None = None,
    ) -> str:
        """Convert ranked articles to compact JSON for the LLM user prompt."""
        limit = max_articles or DEFAULT_MAX_ARTICLES
        summary_limit = summary_chars or MAX_SUMMARY_CHARS
        payload = [
            self._article_payload(article, summary_chars=summary_limit)
            for article in articles[:limit]
        ]
        return json.dumps(payload, separators=(",", ":"), default=str)

    def build_fallback_newsletter(self, articles: list[NewsArticle]) -> str:
        """Deterministic digest when the LLM is unavailable or over token limits."""
        date_str = local_datetime_str("%B %d, %Y")
        lines = [
            f"# AI News Digest — {date_str}",
            "",
            f"Top {min(len(articles), DEFAULT_MAX_ARTICLES)} stories from today's AI news.",
            "",
        ]
        for index, article in enumerate(articles[:DEFAULT_MAX_ARTICLES], start=1):
            summary = (article.summary or "")[:400]
            lines.extend([
                f"## {index}. {article.title}",
                f"**{article.source}** · Importance: {article.importance_score}",
                "",
                summary,
                "",
                f"[Read more]({article.link})",
                "",
            ])
        return self.format_as_markdown("\n".join(lines))

    def _build_budgeted_prompts(
        self,
        articles: list[NewsArticle],
    ) -> tuple[str, str, dict[str, Any]]:
        system_prompt = self.create_system_prompt()
        date_str = local_datetime_str("%B %d, %Y")
        candidates = self._candidate_payloads(articles)

        user_prompt, budget_meta = fit_user_prompt_to_budget(
            system_prompt=system_prompt,
            date_str=date_str,
            article_payloads=candidates,
            format_user_prompt=format_writer_user_prompt,
            max_input_tokens=self.max_input_tokens,
        )

        budget_meta["user_prompt_chars"] = len(user_prompt)
        budget_meta["system_prompt_chars"] = len(system_prompt)
        budget_meta["provider"] = self.provider
        return system_prompt, user_prompt, budget_meta

    def call_llm(self, system_prompt: str, user_prompt: str) -> AIMessage:
        """Invoke Gemini with retries and optional fallback model on 503/429."""
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        estimated_tokens = estimate_messages_tokens(system_prompt, user_prompt)
        models_to_try = [self.model]
        fallback = (DEFAULT_FALLBACK_MODEL or "").strip()
        if fallback and fallback != self.model:
            models_to_try.append(fallback)

        last_error: Exception | None = None
        for model_name in models_to_try:
            llm = self.llm if model_name == self.model else self._build_llm(model_name)
            logger.info(
                "writer.llm_invoke",
                provider=self.provider,
                model=model_name,
                temperature=self.temperature,
                estimated_input_tokens=estimated_tokens,
                max_input_tokens=self.max_input_tokens,
                user_prompt_chars=len(user_prompt),
                system_prompt_chars=len(system_prompt),
            )
            for attempt in range(LLM_MAX_RETRIES):
                try:
                    response = llm.invoke(messages)
                    usage = extract_usage_metadata(response)
                    if usage:
                        logger.info(
                            "writer.llm_usage",
                            provider=self.provider,
                            model=model_name,
                            **usage,
                        )
                    return response
                except Exception as exc:
                    last_error = exc
                    if (
                        self._is_transient_llm_error(exc)
                        and attempt < LLM_MAX_RETRIES - 1
                    ):
                        wait = LLM_RETRY_BASE_SECONDS * (2 ** attempt)
                        logger.warning(
                            "writer.llm_retry",
                            provider=self.provider,
                            model=model_name,
                            attempt=attempt + 1,
                            wait_seconds=wait,
                            error=str(exc),
                        )
                        time.sleep(wait)
                        continue
                    logger.warning(
                        "writer.llm_model_failed",
                        provider=self.provider,
                        model=model_name,
                        error=str(exc),
                    )
                    break

        if last_error:
            raise last_error
        raise RuntimeError("LLM invocation failed without an exception")

    def call_groq_llm(self, system_prompt: str, user_prompt: str) -> AIMessage:
        """Backward-compatible alias for tests and older callers."""
        return self.call_llm(system_prompt, user_prompt)

    @staticmethod
    def format_as_markdown(text: str) -> str:
        """Ensure LLM output is clean markdown."""
        if not text:
            return ""

        cleaned = text.strip()

        fence_match = re.match(r"^```(?:markdown)?\s*\n(.*)\n```\s*$", cleaned, re.DOTALL)
        if fence_match:
            cleaned = fence_match.group(1).strip()

        if not cleaned.startswith("#"):
            cleaned = f"# AI News Newsletter\n\n{cleaned}"

        return cleaned

    def write_newsletter(self, ranked_articles: list[NewsArticle]) -> str:
        """Generate markdown newsletter from top ranked articles."""
        start = time.monotonic()

        if not ranked_articles:
            logger.warning("writer.no_articles")
            return self.format_as_markdown(
                f"# AI News Newsletter\n\n"
                f"*{local_datetime_str('%B %d, %Y')}*\n\n"
                f"No articles available for today's digest."
            )

        system_prompt, user_prompt, budget_meta = self._build_budgeted_prompts(
            ranked_articles
        )
        logger.info(
            "writer.generating",
            article_count=len(ranked_articles),
            model=self.model,
            **budget_meta,
        )

        if not budget_meta.get("within_budget"):
            logger.warning(
                "writer.prompt_over_budget_using_fallback",
                **budget_meta,
            )
            return self.build_fallback_newsletter(ranked_articles)

        try:
            response = self.call_llm(system_prompt, user_prompt)
            raw_content = extract_llm_text(response)
            if not raw_content:
                logger.warning(
                    "writer.empty_llm_response",
                    provider=self.provider,
                    model=self.model,
                    content_repr=repr(getattr(response, "content", ""))[:300],
                    additional_keys=list(
                        (getattr(response, "additional_kwargs", {}) or {}).keys()
                    ),
                )
                newsletter = self.build_fallback_newsletter(ranked_articles)
            else:
                newsletter = self.format_as_markdown(raw_content)
        except Exception as e:
            logger.exception(
                "writer.llm_failed_using_fallback",
                provider=self.provider,
                error=str(e),
                error_type=type(e).__name__,
                article_count=len(ranked_articles),
                **budget_meta,
            )
            newsletter = self.build_fallback_newsletter(ranked_articles)

        duration = time.monotonic() - start
        logger.info(
            "writer.complete",
            provider=self.provider,
            word_count=len(newsletter.split()),
            duration=round(duration, 2),
            estimated_input_tokens=budget_meta.get("estimated_input_tokens"),
        )
        return newsletter

    async def write(self, articles: list[NewsArticle]) -> str:
        """Async entry point used by the LangGraph orchestrator."""
        system_prompt, user_prompt, budget_meta = self._build_budgeted_prompts(articles)

        logger.info(
            "writer.generating_async",
            article_count=len(articles),
            model=self.model,
            **budget_meta,
        )

        if not budget_meta.get("within_budget"):
            return self.build_fallback_newsletter(articles)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]
        response = await self.llm.ainvoke(messages)
        usage = extract_usage_metadata(response)
        if usage:
            logger.info("writer.llm_usage", provider=self.provider, **usage)

        raw_content = extract_llm_text(response)
        if not raw_content:
            logger.warning(
                "writer.empty_llm_response_async",
                provider=self.provider,
                model=self.model,
            )
            return self.build_fallback_newsletter(articles)
        return self.format_as_markdown(raw_content)
