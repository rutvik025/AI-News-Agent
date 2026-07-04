# AI News Aggregator & Newsletter System

An autonomous multi-agent system that collects AI news from 50+ RSS sources, deduplicates using semantic similarity, ranks by importance, generates professional newsletters with Google Gemini, and delivers via Telegram and email.

## Architecture

```
Collector → Deduplicator → Ranker → Writer → Delivery
   (RSS)    (ChromaDB)    (scoring)  (Gemini)  (Telegram/Email)
```

Built with **LangGraph** for orchestration and **MCP** servers for modular tool exposure.

| Agent | LLM | Purpose |
|-------|-----|---------|
| Collector | No | Fetch 50+ RSS feeds concurrently |
| Deduplicator | No | Semantic dedup via ChromaDB (threshold 0.85) |
| Ranker | No | Score by freshness, credibility, relevance |
| Writer | Yes (Gemini) | Generate markdown newsletter |
| Delivery | No | Send to Telegram + Email |

## Quick Start

### 1. Setup

```bash
cd ai-news-agent
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
```

### 2. Configure

Edit `.env` with required credentials:

- `GEMINI_API_KEY` — [Google AI Studio](https://aistudio.google.com/apikey)
- `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHANNEL_ID` — Telegram Bot API
- `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_RECIPIENTS` — SMTP credentials for email delivery

### 3. Run

```bash
# Full pipeline (collect → deduplicate → rank → write → deliver)
python main.py

# Daily scheduler (6:00 AM IST)
python deploy/cron_scheduler.py

# LangGraph CLI
langgraph dev
```

## Project Structure

```
ai-news-agent/
├── src/
│   ├── collector_agent.py      # RSS collection (aiohttp + feedparser)
│   ├── deduplicator_agent.py     # ChromaDB semantic dedup
│   ├── ranker_agent.py           # Importance scoring
│   ├── writer_agent.py           # Gemini LLM newsletter generation
│   ├── delivery_agent.py         # Telegram + Email delivery
│   ├── orchestrator.py           # LangGraph 5-node workflow
│   ├── schemas.py                # Pydantic models
│   ├── utils/                    # Embeddings, scoring, logging, paths
│   └── prompts/                  # Writer system prompt
├── config/
│   ├── rss_sources.yaml          # 60 RSS feeds across 6 categories
│   ├── delivery_config.yaml
│   └── topics_config.yaml
├── tests/                        # pytest unit + integration tests
├── deploy/                       # Docker, Render, cron scheduler
└── outputs/                      # Newsletters, logs, ChromaDB
```

## Key Metrics

| Metric | Target |
|--------|--------|
| RSS Sources | 50+ feeds |
| Articles Collected | 200–500/day |
| After Deduplication | 100–200 unique |
| Final Newsletter | Top 20 articles |
| Collection Time | < 2 minutes |
| Newsletter Generation | < 5 minutes |

## Scoring Formula

```
importance = 0.4 × freshness + 0.3 × credibility + 0.3 × relevance
```

- **Freshness**: 1.0 (today) → 0.1 (month+ old)
- **Credibility**: Source reputation (ArXiv=1.0, Reddit=0.65)
- **Relevance**: AI keyword density from `topics_config.yaml`

## Output Files

After a successful run:

```
outputs/newsletters/YYYY-MM-DD_newsletter.md
outputs/newsletters/YYYY-MM-DD_newsletter.html
outputs/logs/pipeline.log
outputs/chroma_db/
```

## Testing

```bash
pytest                          # All tests
pytest tests/test_collector.py  # Single agent
pytest -m integration           # Integration tests only
```

## Docker Deployment

```bash
cd deploy
docker-compose up -d
```

## Render Deployment

```bash
# Connect repo to Render, uses deploy/render.yaml
render deploy
```

## Environment Variables

See `.env.example` for the full list. Never commit `.env` to version control.

## Tech Stack

- **Python 3.11+** with AsyncIO
- **LangGraph** — agent orchestration
- **Google Gemini** — LLM (gemini-3.5-flash)
- **feedparser** + **readability-lxml** + **newspaper3k** — content parsing
- **sentence-transformers** (nomic-embed-text-v1) — embeddings
- **ChromaDB** — vector storage for dedup
- **aiohttp** — async HTTP (10 concurrent, 0.5s rate limit)

## License

MIT
