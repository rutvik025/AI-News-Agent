"""LangGraph orchestrator — 5-agent sequential workflow with checkpoint/resume.



START → Collector → Deduplicator → Ranker → Writer → Delivery → END



Checkpoints are stored in SQLite (LangGraph) plus JSON snapshots per node for

manual resume (e.g. retry writer after Gemini 503 without re-collecting RSS).

"""

from __future__ import annotations


import asyncio

import os

import time

from typing import Any, TypedDict


from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from langgraph.graph import END, StateGraph


from src.collector_agent import CollectorAgent

from src.deduplicator_agent import DeduplicatorAgent

from src.delivery_agent import DeliveryAgent

from src.ranker_agent import RankerAgent

from src.schemas import OrchestratorState

from src.utils.logger import get_logger

from src.utils.pipeline_checkpoint import (
    PIPELINE_NODES,
    articles_from_dicts,
    articles_to_dicts,
    checkpoint_db_path,
    clear_thread_state,
    default_thread_id,
    load_snapshot_for_resume,
    save_node_snapshot,
)

from src.writer_agent import WriterAgent


logger = get_logger(__name__)


RECURSION_LIMIT = 200


class GraphState(TypedDict, total=False):

    topics: list[str]

    resume_from: str

    pipeline_completed: bool

    collected_news: list[dict[str, Any]]

    deduplicated_news: list[dict[str, Any]]

    ranked_news: list[dict[str, Any]]

    newsletter: str

    delivery_status: dict[str, bool]

    errors: list[str]

    metadata: dict[str, Any]


def _initial_graph_state(topics: list[str] | None = None) -> GraphState:

    return {
        "topics": topics or [],
        "resume_from": "",
        "pipeline_completed": False,
        "collected_news": [],
        "deduplicated_news": [],
        "ranked_news": [],
        "newsletter": "",
        "delivery_status": {},
        "errors": [],
        "metadata": {},
    }


def _to_orchestrator_state(
    final_state: GraphState,
    total_duration: float,
) -> OrchestratorState:

    return OrchestratorState(
        topics=final_state.get("topics", []),
        collected_news=articles_from_dicts(final_state.get("collected_news")),
        deduplicated_news=articles_from_dicts(final_state.get("deduplicated_news")),
        ranked_news=articles_from_dicts(final_state.get("ranked_news")),
        newsletter=final_state.get("newsletter", ""),
        delivery_status=final_state.get("delivery_status", {}),
        errors=final_state.get("errors", []),
        metadata={
            **final_state.get("metadata", {}),
            "total_duration": total_duration,
        },
    )


def _entry_router(state: GraphState) -> str:

    resume_from = (state.get("resume_from") or "").strip()

    if resume_from in PIPELINE_NODES:

        return resume_from

    return "collector"


class Orchestrator:
    """Orchestrates the 5-agent pipeline using LangGraph StateGraph."""

    def __init__(
        self,
        collector: CollectorAgent | None = None,
        deduplicator: DeduplicatorAgent | None = None,
        ranker: RankerAgent | None = None,
        writer: WriterAgent | None = None,
        delivery: DeliveryAgent | None = None,
        thread_id: str | None = None,
    ) -> None:

        self.collector = collector or CollectorAgent()

        self.deduplicator = deduplicator or DeduplicatorAgent()

        self.ranker = ranker or RankerAgent()

        self.writer = writer or WriterAgent()

        self.delivery = delivery or DeliveryAgent()

        self.thread_id = thread_id or default_thread_id()

        self._graph = None

    def _checkpoint_config(self) -> dict[str, Any]:

        return {
            "recursion_limit": RECURSION_LIMIT,
            "configurable": {"thread_id": self.thread_id},
        }

    def _save_snapshot(self, node: str, state: GraphState) -> None:

        save_node_snapshot(self.thread_id, node, dict(state))

    async def _collector_node(self, state: GraphState) -> dict[str, Any]:

        logger.info("orchestrator.node", node="collector")

        try:

            articles = await self.collector.collect_news()

            result: dict[str, Any] = {
                "collected_news": articles_to_dicts(articles),
                "metadata": {
                    **state.get("metadata", {}),
                    "collection": {
                        "article_count": len(articles),
                        "sources_fetched": (
                            self.collector._last_sources_count
                            - len(self.collector.failed_sources)
                        ),
                        "sources_failed": len(self.collector.failed_sources),
                        "failed_sources": self.collector.failed_sources,
                    },
                },
            }

            self._save_snapshot("collector", {**state, **result})

            logger.info(
                "orchestrator.collector_done",
                article_count=len(articles),
                sources_failed=self.collector.failed_sources,
            )

            return result

        except Exception as e:

            logger.exception(
                "orchestrator.collector_failed",
                error=str(e),
                error_type=type(e).__name__,
            )

            return {"errors": state.get("errors", []) + [f"collector: {e}"]}

    async def _deduplicator_node(self, state: GraphState) -> dict[str, Any]:

        logger.info("orchestrator.node", node="deduplicator")

        try:

            collected = articles_from_dicts(state.get("collected_news"))

            before = len(collected)

            articles = self.deduplicator.deduplicate_news(collected)

            result: dict[str, Any] = {
                "deduplicated_news": articles_to_dicts(articles),
                "metadata": {
                    **state.get("metadata", {}),
                    "deduplication": {
                        "input_count": before,
                        "output_count": len(articles),
                        "duplicates_removed": before - len(articles),
                    },
                },
            }

            self._save_snapshot("deduplicator", {**state, **result})

            return result

        except Exception as e:

            logger.exception(
                "orchestrator.deduplicator_failed",
                error=str(e),
                error_type=type(e).__name__,
            )

            return {"errors": state.get("errors", []) + [f"deduplicator: {e}"]}

    async def _ranker_node(self, state: GraphState) -> dict[str, Any]:

        logger.info("orchestrator.node", node="ranker")

        try:

            topics = state.get("topics", [])

            deduped = articles_from_dicts(state.get("deduplicated_news"))

            articles = self.ranker.rank_news(deduped, topics=topics if topics else None)

            result: dict[str, Any] = {
                "ranked_news": articles_to_dicts(articles),
                "metadata": {
                    **state.get("metadata", {}),
                    "ranking": {
                        "top_n": len(articles),
                        "topics_used": topics,
                    },
                },
            }

            self._save_snapshot("ranker", {**state, **result})

            return result

        except Exception as e:

            logger.exception(
                "orchestrator.ranker_failed",
                error=str(e),
                error_type=type(e).__name__,
            )

            return {"errors": state.get("errors", []) + [f"ranker: {e}"]}

    async def _writer_node(self, state: GraphState) -> dict[str, Any]:

        logger.info("orchestrator.node", node="writer")

        try:

            ranked = articles_from_dicts(state.get("ranked_news"))

            newsletter = self.writer.write_newsletter(ranked)

            result: dict[str, Any] = {
                "newsletter": newsletter,
                "metadata": {
                    **state.get("metadata", {}),
                    "writer": {"word_count": len(newsletter.split())},
                },
            }

            self._save_snapshot("writer", {**state, **result})

            return result

        except Exception as e:

            logger.exception(
                "orchestrator.writer_failed",
                error=str(e),
                error_type=type(e).__name__,
            )

            ranked = articles_from_dicts(state.get("ranked_news"))

            fallback = self.writer.build_fallback_newsletter(ranked) if ranked else ""

            return {
                "newsletter": fallback,
                "errors": state.get("errors", []) + [f"writer: {e}"],
            }

    async def _delivery_node(self, state: GraphState) -> dict[str, Any]:

        logger.info("orchestrator.node", node="delivery")

        try:

            newsletter = (state.get("newsletter") or "").strip()

            ranked = articles_from_dicts(state.get("ranked_news"))

            if not newsletter and ranked:

                newsletter = self.writer.build_fallback_newsletter(ranked)

                logger.warning(
                    "delivery.using_fallback_newsletter",
                    reason="writer_returned_empty",
                    chars=len(newsletter),
                )

            status = await self.delivery.deliver_newsletter(newsletter)

            result: dict[str, Any] = {
                "newsletter": newsletter,
                "pipeline_completed": True,
                "delivery_status": {
                    "telegram": bool(status.get("telegram")),
                    "email": bool(status.get("email")),
                },
                "metadata": {
                    **state.get("metadata", {}),
                    "delivery": {
                        "newsletter_path": status.get("newsletter_path"),
                        "html_path": status.get("html_path"),
                        "newsletter_chars": len(newsletter),
                        "email_sent": bool(status.get("email")),
                        "telegram_sent": bool(status.get("telegram")),
                    },
                },
            }

            self._save_snapshot("delivery", {**state, **result})

            return result

        except Exception as e:

            logger.exception(
                "orchestrator.delivery_failed",
                error=str(e),
                error_type=type(e).__name__,
            )

            return {
                "delivery_status": {"telegram": False, "email": False},
                "errors": state.get("errors", []) + [f"delivery: {e}"],
            }

    def build_orchestrator_graph(self, checkpointer: Any = None) -> Any:
        """Build and compile the LangGraph StateGraph workflow."""

        workflow = StateGraph(GraphState)

        workflow.add_node("collector", self._collector_node)

        workflow.add_node("deduplicator", self._deduplicator_node)

        workflow.add_node("ranker", self._ranker_node)

        workflow.add_node("writer", self._writer_node)

        workflow.add_node("delivery", self._delivery_node)

        workflow.set_conditional_entry_point(
            _entry_router,
            {node: node for node in PIPELINE_NODES},
        )

        workflow.add_edge("collector", "deduplicator")

        workflow.add_edge("deduplicator", "ranker")

        workflow.add_edge("ranker", "writer")

        workflow.add_edge("writer", "delivery")

        workflow.add_edge("delivery", END)

        return workflow.compile(checkpointer=checkpointer)

    async def arun(
        self,
        topics: list[str] | None = None,
        *,
        mode: str | None = None,
        from_node: str | None = None,
    ) -> OrchestratorState:
        """Execute the workflow asynchronously with optional resume."""

        start = time.monotonic()

        pipeline_mode = (mode or os.getenv("PIPELINE_MODE", "auto")).lower()

        resume_from = (from_node or os.getenv("PIPELINE_FROM_NODE", "")).strip()

        logger.info(
            "orchestrator.start",
            topics=topics or [],
            thread_id=self.thread_id,
            mode=pipeline_mode,
            from_node=resume_from or None,
        )

        db_path = checkpoint_db_path()

        db_path.parent.mkdir(parents=True, exist_ok=True)

        async with AsyncSqliteSaver.from_conn_string(str(db_path)) as checkpointer:

            graph = self.build_orchestrator_graph(checkpointer=checkpointer)

            config = self._checkpoint_config()

            if pipeline_mode == "fresh":

                clear_thread_state(self.thread_id)

                await checkpointer.adelete_thread(self.thread_id)

                initial_state = _initial_graph_state(topics)

                logger.info("orchestrator.fresh_run", thread_id=self.thread_id)

            elif resume_from:

                loaded = load_snapshot_for_resume(self.thread_id, resume_from)

                if not loaded:

                    raise RuntimeError(
                        f"No snapshot found to resume from node '{resume_from}' "
                        f"for thread '{self.thread_id}'. Run a full pipeline first."
                    )

                initial_state = loaded

                if topics:

                    initial_state["topics"] = topics

                logger.info(
                    "orchestrator.resume_from_node",
                    from_node=resume_from,
                    thread_id=self.thread_id,
                )

            else:

                snapshot = await graph.aget_state(config)

                pending_nodes = snapshot.next or ()

                if pipeline_mode in {"resume", "auto"} and pending_nodes:

                    logger.info(
                        "orchestrator.langgraph_resume",
                        thread_id=self.thread_id,
                        pending_nodes=list(pending_nodes),
                    )

                    final_state = await graph.ainvoke(None, config=config)

                    duration = time.monotonic() - start

                    return _to_orchestrator_state(final_state, duration)

                if (
                    pipeline_mode == "resume"
                    and snapshot.values
                    and snapshot.values.get("pipeline_completed")
                ):

                    logger.info(
                        "orchestrator.already_completed",
                        thread_id=self.thread_id,
                    )

                    duration = time.monotonic() - start

                    return _to_orchestrator_state(snapshot.values, duration)

                initial_state = _initial_graph_state(topics)

            final_state = await graph.ainvoke(initial_state, config=config)

        duration = time.monotonic() - start

        result = _to_orchestrator_state(final_state, duration)

        logger.info(
            "orchestrator.complete",
            collected=len(result.collected_news),
            deduplicated=len(result.deduplicated_news),
            ranked=len(result.ranked_news),
            newsletter_chars=len(result.newsletter),
            delivery=result.delivery_status,
            errors=len(result.errors),
            duration=round(duration, 2),
            thread_id=self.thread_id,
        )

        return result

    def run(
        self,
        topics: list[str] | None = None,
        *,
        mode: str | None = None,
        from_node: str | None = None,
    ) -> OrchestratorState:
        """Execute the full workflow and return final OrchestratorState."""

        return asyncio.run(self.arun(topics, mode=mode, from_node=from_node))


# Backward-compatible alias

NewsOrchestrator = Orchestrator


def build_graph() -> Any:
    """Entry point for langgraph.json."""

    return Orchestrator().build_orchestrator_graph()


def build_orchestrator_graph(
    collector: CollectorAgent | None = None,
    deduplicator: DeduplicatorAgent | None = None,
    ranker: RankerAgent | None = None,
    writer: WriterAgent | None = None,
    delivery: DeliveryAgent | None = None,
    checkpointer: Any = None,
) -> Any:
    """Build orchestrator graph with optional custom agents."""

    return Orchestrator(
        collector=collector,
        deduplicator=deduplicator,
        ranker=ranker,
        writer=writer,
        delivery=delivery,
    ).build_orchestrator_graph(checkpointer=checkpointer)
