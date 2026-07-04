"""Priority-based RSS source loading and filtering."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.schemas import RSSSource, UpdateFrequency
from src.utils.logger import get_logger
from src.utils.paths import resolve_path

logger = get_logger(__name__)

FREQUENCY_HOURS = {
    UpdateFrequency.HOURLY: 1,
    UpdateFrequency.DAILY: 24,
    UpdateFrequency.WEEKLY: 168,
}


class SourcePrioritizer:
    """Load, filter, and sort RSS sources by priority and update frequency."""

    def __init__(self, config_path: str | Path = "config/rss_sources.yaml") -> None:
        self.config_path = resolve_path(config_path)

    def load_sources(self) -> list[RSSSource]:
        if not self.config_path.exists():
            raise FileNotFoundError(f"RSS sources config not found: {self.config_path}")

        with self.config_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)

        sources = [RSSSource(**s) for s in data.get("sources", [])]
        logger.info("sources.loaded", count=len(sources))
        return sources

    def filter_active_sources(
        self,
        sources: list[RSSSource],
        last_run: datetime | None = None,
    ) -> list[RSSSource]:
        """Filter sources that are active and due for update based on frequency."""
        now = datetime.now(timezone.utc)
        active = [s for s in sources if s.active]

        if last_run is None:
            filtered = active
        else:
            filtered = []
            last_run_utc = last_run.replace(tzinfo=timezone.utc)
            for source in active:
                hours_since = (now - last_run_utc).total_seconds() / 3600
                required_hours = FREQUENCY_HOURS.get(source.update_frequency, 24)
                if hours_since >= required_hours:
                    filtered.append(source)

        logger.info(
            "sources.filtered",
            total=len(sources),
            active=len(active),
            due=len(filtered),
        )
        return filtered

    def sort_by_priority(self, sources: list[RSSSource]) -> list[RSSSource]:
        """Sort sources by priority (1=critical first), then credibility descending."""
        return sorted(sources, key=lambda s: (s.priority, -s.credibility))


def load_rss_sources(config_path: str | Path = "config/rss_sources.yaml") -> list[RSSSource]:
    return SourcePrioritizer(config_path).load_sources()


def filter_active_sources(
    sources: list[RSSSource],
    last_run: datetime | None = None,
) -> list[RSSSource]:
    return SourcePrioritizer().filter_active_sources(sources, last_run)


def sort_by_priority(sources: list[RSSSource]) -> list[RSSSource]:
    return SourcePrioritizer().sort_by_priority(sources)
