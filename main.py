"""Main entry point for the AI News Aggregator."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

from src.utils.paths import PROJECT_ROOT, resolve_path

# Ensure imports and relative config paths resolve to ai-news-agent/
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from src.orchestrator import Orchestrator
from src.utils.logger import get_logger, setup_logging
from src.utils.pipeline_checkpoint import default_thread_id
from src.utils.timezone_utils import configure_timezone, local_date_str, now_local


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI News Aggregator pipeline")
    parser.add_argument(
        "--mode",
        choices=("auto", "fresh", "resume"),
        default=None,
        help=(
            "auto: resume interrupted LangGraph checkpoint if present, else fresh run; "
            "fresh: ignore checkpoints and re-collect everything; "
            "resume: continue from last checkpoint/snapshot"
        ),
    )
    parser.add_argument(
        "--from-node",
        choices=("collector", "deduplicator", "ranker", "writer", "delivery"),
        default=None,
        help="Start from a saved snapshot (e.g. writer after Gemini 503)",
    )
    parser.add_argument(
        "--thread-id",
        default=None,
        help="Pipeline thread/checkpoint id (default: pipeline-YYYY-MM-DD)",
    )
    return parser.parse_args()


async def main() -> None:
    setup_logging()
    configure_timezone()
    logger = get_logger(__name__)
    args = _parse_args()

    thread_id = args.thread_id or default_thread_id()
    mode = args.mode or os.getenv("PIPELINE_MODE", "auto")

    logger.info(
        "main.start",
        message="AI News Aggregator starting",
        project_root=str(PROJECT_ROOT),
        timezone=now_local().tzinfo,
        local_time=now_local().isoformat(),
        thread_id=thread_id,
        mode=mode,
        from_node=args.from_node,
    )

    orchestrator = Orchestrator(thread_id=thread_id)
    result = await orchestrator.arun(mode=mode, from_node=args.from_node)

    newsletter_path = (result.metadata.get("delivery") or {}).get("newsletter_path")
    if not newsletter_path and result.newsletter.strip():
        newsletter_path = str(
            resolve_path("outputs/newsletters") / f"{local_date_str()}_newsletter.md"
        )

    logger.info(
        "main.complete",
        collected=len(result.collected_news),
        deduplicated=len(result.deduplicated_news),
        ranked=len(result.ranked_news),
        newsletter_length=len(result.newsletter),
        newsletter_path=newsletter_path,
        delivery=result.delivery_status,
        errors=result.errors,
        metadata=result.metadata,
        thread_id=thread_id,
    )

    if result.errors:
        logger.error("main.errors", errors=result.errors, count=len(result.errors))

    if not result.newsletter.strip():
        logger.error("main.no_newsletter_generated")
        print("\nPipeline finished but no newsletter content was generated.")
        print("  Check outputs/logs/pipeline.log for writer details.")
        print(f"  Retry writer only: python main.py --from-node writer --thread-id {thread_id}")
        sys.exit(1)

    if result.errors and not any(result.delivery_status.values()):
        sys.exit(1)

    if result.errors:
        logger.warning(
            "main.partial_success",
            message="Pipeline completed with errors but newsletter was saved",
            delivery=result.delivery_status,
        )

    print("\nNewsletter generated successfully!")
    print(f"  Local time (IST): {now_local().strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"  Thread: {thread_id}")
    print(f"  Collected: {len(result.collected_news)} articles")
    print(f"  After dedup: {len(result.deduplicated_news)} articles")
    print(f"  Ranked top: {len(result.ranked_news)} articles")
    print(f"  Newsletter: {len(result.newsletter)} characters")
    if newsletter_path:
        print(f"  Saved to: {newsletter_path}")
        print(f"  HTML copy: {str(newsletter_path).replace('.md', '.html')}")
    print(f"  Telegram: {result.delivery_status.get('telegram')}")
    print(f"  Email: {result.delivery_status.get('email')}")
    print(f"\n  Resume writer only: python main.py --from-node writer --thread-id {thread_id}")


if __name__ == "__main__":
    asyncio.run(main())
