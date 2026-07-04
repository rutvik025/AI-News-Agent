# Graph Report - ai-news-agent  (2026-07-04)

## Corpus Check
- 39 files · ~14,440 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 446 nodes · 1027 edges · 22 communities (14 shown, 8 thin omitted)
- Extraction: 80% EXTRACTED · 20% INFERRED · 0% AMBIGUOUS · INFERRED: 209 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]

## God Nodes (most connected - your core abstractions)
1. `NewsArticle` - 71 edges
2. `CollectorAgent` - 50 edges
3. `RSSSource` - 30 edges
4. `EmbeddingGenerator` - 30 edges
5. `WriterAgent` - 30 edges
6. `Orchestrator` - 28 edges
7. `DeduplicatorAgent` - 25 edges
8. `DeliveryAgent` - 22 edges
9. `RankerAgent` - 22 edges
10. `resolve_path()` - 22 edges

## Surprising Connections (you probably didn't know these)
- `Namespace` --uses--> `Orchestrator`  [INFERRED]
  main.py → src/orchestrator.py
- `Path` --uses--> `NewsArticle`  [INFERRED]
  conftest.py → src/schemas.py
- `RSSSource` --uses--> `NewsArticle`  [INFERRED]
  conftest.py → src/schemas.py
- `NewsArticle` --uses--> `NewsArticle`  [INFERRED]
  conftest.py → src/schemas.py
- `CollectorAgent` --uses--> `CollectorAgent`  [INFERRED]
  tests/test_collector.py → src/collector_agent.py

## Import Cycles
- 1-file cycle: `src/utils/timezone_utils.py -> src/utils/timezone_utils.py`
- 1-file cycle: `src/utils/scoring.py -> src/utils/scoring.py`
- 1-file cycle: `src/utils/source_prioritizer.py -> src/utils/source_prioritizer.py`

## Communities (22 total, 8 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.08
Nodes (42): DeduplicatorAgent, DeliveryAgent, Orchestrator, OrchestratorState, RankerAgent, build_graph(), build_orchestrator_graph(), _entry_router() (+34 more)

### Community 1 - "Community 1"
Cohesion: 0.06
Nodes (38): CollectionResult, NewsArticle, Path, RSSSource, Pytest configuration and shared fixtures., rss_sources_config(), sample_articles(), sample_source() (+30 more)

### Community 2 - "Community 2"
Cohesion: 0.07
Nodes (35): BaseModel, Enum, format_writer_user_prompt(), Writer prompts sized for Gemini input token limits., Compact user prompt — minimal wrapper, dense JSON payload., RankingResult, NewsArticle, Path (+27 more)

### Community 3 - "Community 3"
Cohesion: 0.08
Nodes (36): BoundLogger, main_async(), Daily cron scheduler — runs the news aggregator at 6:00 AM IST., main(), _parse_args(), Main entry point for the AI News Aggregator., Namespace, Delivery Agent — sends newsletter via Telegram and Email. (+28 more)

### Community 4 - "Community 4"
Cohesion: 0.08
Nodes (28): AIMessage, ChatGoogleGenerativeAI, Exception, Any, Any, NewsArticle, Return the system prompt for newsletter generation., Build progressively smaller article payloads for token budgeting. (+20 more)

### Community 5 - "Community 5"
Cohesion: 0.10
Nodes (19): ClientSession, CollectorAgent, Any, NewsArticle, RSSSource, Clean HTML using readability-lxml (not BeautifulSoup)., Parse RSS entry timestamp to ISO format., Extract and clean content from an RSS entry with fallbacks. (+11 more)

### Community 6 - "Community 6"
Cohesion: 0.14
Nodes (13): Collection, DeduplicationResult, DeduplicatorAgent, EmbeddingGenerator, NewsArticle, Deduplicator Agent — semantic similarity deduplication with ChromaDB., Remove duplicate articles (orchestrator entry point)., Clear ChromaDB collection (for testing). (+5 more)

### Community 7 - "Community 7"
Cohesion: 0.18
Nodes (6): collector(), CollectorAgent, RSSSource, Tests for Collector Agent., sample_source(), TestCollectorAgent

### Community 8 - "Community 8"
Cohesion: 0.11
Nodes (18): AI Agent Rules, API Conventions, Backend Root-Level Files, Backend Rules, Configuration & Environments, Database Rules, Engineering Standards, Error Handling & Logging (+10 more)

### Community 9 - "Community 9"
Cohesion: 0.12
Nodes (16): 1. Setup, 2. Configure, 3. Run, AI News Aggregator & Newsletter System, Architecture, Docker Deployment, Environment Variables, Key Metrics (+8 more)

### Community 10 - "Community 10"
Cohesion: 0.21
Nodes (5): MIMEMultipart, DeliveryAgent, Path, Deliver newsletter to Telegram channel and email recipients., Save and deliver newsletter via Telegram and email (orchestrator entry point).

### Community 12 - "Community 12"
Cohesion: 0.40
Nodes (4): dependencies, env, graphs, news_orchestrator

## Knowledge Gaps
- **40 isolated node(s):** `PreToolUse`, `PreToolUse`, `dependencies`, `news_orchestrator`, `env` (+35 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `NewsArticle` connect `Community 2` to `Community 0`, `Community 1`, `Community 3`, `Community 4`, `Community 5`, `Community 6`, `Community 7`, `Community 11`?**
  _High betweenness centrality (0.284) - this node is a cross-community bridge._
- **Why does `CollectorAgent` connect `Community 5` to `Community 0`, `Community 1`, `Community 2`, `Community 7`?**
  _High betweenness centrality (0.159) - this node is a cross-community bridge._
- **Why does `WriterAgent` connect `Community 4` to `Community 0`, `Community 2`, `Community 11`?**
  _High betweenness centrality (0.088) - this node is a cross-community bridge._
- **Are the 52 inferred relationships involving `NewsArticle` (e.g. with `AIMessage` and `ChatGoogleGenerativeAI`) actually correct?**
  _`NewsArticle` has 52 INFERRED edges - model-reasoned connections that need verification._
- **Are the 20 inferred relationships involving `CollectorAgent` (e.g. with `DeduplicatorAgent` and `DeliveryAgent`) actually correct?**
  _`CollectorAgent` has 20 INFERRED edges - model-reasoned connections that need verification._
- **Are the 22 inferred relationships involving `RSSSource` (e.g. with `ClientSession` and `CollectionResult`) actually correct?**
  _`RSSSource` has 22 INFERRED edges - model-reasoned connections that need verification._
- **Are the 17 inferred relationships involving `EmbeddingGenerator` (e.g. with `ClientSession` and `Collection`) actually correct?**
  _`EmbeddingGenerator` has 17 INFERRED edges - model-reasoned connections that need verification._