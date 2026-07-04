"""Extract usable text and usage metadata from LangChain chat responses."""

from __future__ import annotations

from typing import Any


def extract_llm_text(response: Any) -> str:
    """Normalize AIMessage content from string, block list, or metadata."""
    content = getattr(response, "content", "")

    if isinstance(content, str) and content.strip():
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str) and item.strip():
                parts.append(item.strip())
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        if parts:
            return "\n".join(parts)

    additional = getattr(response, "additional_kwargs", {}) or {}
    for key in ("content", "text", "output", "completion"):
        value = additional.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    metadata = getattr(response, "response_metadata", {}) or {}
    if isinstance(metadata, dict):
        for key in ("content", "text", "output"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        message = metadata.get("message")
        if isinstance(message, dict):
            message_content = message.get("content")
            if isinstance(message_content, str) and message_content.strip():
                return message_content.strip()

    return ""


def extract_usage_metadata(response: Any) -> dict[str, int]:
    """Extract token usage from LangChain AIMessage metadata when available."""
    usage: dict[str, int] = {}

    response_metadata = getattr(response, "response_metadata", {}) or {}
    if isinstance(response_metadata, dict):
        token_usage = response_metadata.get("token_usage") or response_metadata.get(
            "usage_metadata"
        )
        if isinstance(token_usage, dict):
            usage = _normalize_usage_dict(token_usage)

        if not usage:
            usage = _normalize_usage_dict(response_metadata)

    usage_metadata = getattr(response, "usage_metadata", None)
    if usage_metadata is not None:
        if hasattr(usage_metadata, "model_dump"):
            usage = _normalize_usage_dict(usage_metadata.model_dump())
        elif isinstance(usage_metadata, dict):
            usage = _normalize_usage_dict(usage_metadata)

    return usage


def _normalize_usage_dict(data: dict[str, Any]) -> dict[str, int]:
    mapping = {
        "input_tokens": ("input_tokens", "prompt_tokens", "prompt_token_count"),
        "output_tokens": (
            "output_tokens",
            "completion_tokens",
            "candidates_token_count",
            "completion_token_count",
        ),
        "total_tokens": ("total_tokens", "total_token_count"),
    }
    normalized: dict[str, int] = {}
    for target, keys in mapping.items():
        for key in keys:
            value = data.get(key)
            if isinstance(value, int):
                normalized[target] = value
                break
    return normalized
