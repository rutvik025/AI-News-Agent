"""Daily cron scheduler — runs the news aggregator at 6:00 AM IST."""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.orchestrator import NewsOrchestrator
from src.utils.logger import get_logger, setup_logging

load_dotenv(PROJECT_ROOT / ".env")

IST = ZoneInfo("Asia/Kolkata")
logger = get_logger(__name__)


async def run_pipeline() -> None:
    logger.info("scheduler.run_start", time=datetime.now(IST).isoformat())
    orchestrator = NewsOrchestrator()
    result = await orchestrator.arun()
    logger.info(
        "scheduler.run_complete",
        collected=len(result.collected_news),
        ranked=len(result.ranked_news),
        delivery=result.delivery_status,
        errors=result.errors,
    )


async def main_async() -> None:
    setup_logging()
    logger.info("scheduler.start", schedule="06:00 IST daily")

    scheduler = AsyncIOScheduler(timezone=IST)
    scheduler.add_job(
        run_pipeline,
        CronTrigger(hour=6, minute=0, timezone=IST),
        id="daily_newsletter",
        name="Daily AI Newsletter",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("scheduler.waiting")

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("scheduler.shutdown")


if __name__ == "__main__":
    asyncio.run(main_async())
