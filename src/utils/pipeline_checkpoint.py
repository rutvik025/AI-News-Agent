"""LangGraph checkpoint helpers and human-readable pipeline state snapshots."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from src.schemas import NewsArticle
from src.utils.logger import get_logger
from src.utils.paths import resolve_path
from src.utils.timezone_utils import local_date_str

logger = get_logger(__name__)

PIPELINE_NODES: tuple[str, ...] = (
    "collector",
    "deduplicator",
    "ranker",
    "writer",
    "delivery",
)

DEFAULT_CHECKPOINT_DB = "outputs/checkpoints/pipeline.db"
DEFAULT_SNAPSHOT_DIR = "outputs/pipeline_state"


def default_thread_id() -> str:
    """One pipeline thread per local calendar day."""
    explicit = os.getenv("PIPELINE_THREAD_ID", "").strip()
    if explicit:
        return explicit
    return f"pipeline-{local_date_str()}"


def checkpoint_db_path() -> Path:
    return resolve_path(os.getenv("PIPELINE_CHECKPOINT_DB", DEFAULT_CHECKPOINT_DB))


def snapshot_dir(thread_id: str) -> Path:
    base = resolve_path(os.getenv("PIPELINE_SNAPSHOT_DIR", DEFAULT_SNAPSHOT_DIR))
    return base / thread_id


def articles_to_dicts(articles: list[NewsArticle]) -> list[dict[str, Any]]:
    return [article.model_dump(mode="json") for article in articles]


def articles_from_dicts(data: list[dict[str, Any]] | None) -> list[NewsArticle]:
    if not data:
        return []
    return [NewsArticle.model_validate(item) for item in data]


def serialize_graph_state(state: dict[str, Any]) -> dict[str, Any]:
    """Convert graph state to JSON-serializable dict."""
    payload = dict(state)
    for key in ("collected_news", "deduplicated_news", "ranked_news"):
        value = payload.get(key)
        if value and isinstance(value[0], NewsArticle):
            payload[key] = articles_to_dicts(value)
    return payload


def save_node_snapshot(thread_id: str, node: str, state: dict[str, Any]) -> Path:
    """Persist readable state after a node completes (resume without re-fetching RSS)."""
    directory = snapshot_dir(thread_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{node}.json"
    payload = {
        "thread_id": thread_id,
        "last_completed_node": node,
        "state": serialize_graph_state(state),
    }
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    logger.info(
        "pipeline.snapshot_saved",
        thread_id=thread_id,
        node=node,
        path=str(path),
    )
    return path


def load_snapshot_for_resume(thread_id: str, from_node: str) -> dict[str, Any] | None:
    """Load state from the last completed node before ``from_node``."""
    if from_node not in PIPELINE_NODES:
        raise ValueError(f"Unknown pipeline node: {from_node}")

    start_index = PIPELINE_NODES.index(from_node)
    if start_index == 0:
        return None

    for node in reversed(PIPELINE_NODES[:start_index]):
        path = snapshot_dir(thread_id) / f"{node}.json"
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            state = payload.get("state", {})
            state["resume_from"] = from_node
            logger.info(
                "pipeline.snapshot_loaded",
                thread_id=thread_id,
                from_node=from_node,
                loaded_after=node,
                path=str(path),
            )
            return state
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "pipeline.snapshot_load_failed",
                path=str(path),
                error=str(exc),
            )
    return None


def previous_node(node: str) -> str | None:
    if node not in PIPELINE_NODES:
        return None
    index = PIPELINE_NODES.index(node)
    return PIPELINE_NODES[index - 1] if index > 0 else None


def clear_thread_state(thread_id: str) -> None:
    """Remove JSON snapshots for a thread (SQLite cleared separately)."""
    directory = snapshot_dir(thread_id)
    if directory.exists():
        for file in directory.glob("*.json"):
            file.unlink()
        logger.info("pipeline.snapshots_cleared", thread_id=thread_id, path=str(directory))
