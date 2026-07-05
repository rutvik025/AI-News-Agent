# AI News Agent & Newsletter Aggregator - Project Report

This document provides a detailed overview of the architecture, tech stack, data flow, and workflow of the AI News Agent project.

---

## 1. System Workflow Diagram

Below is the complete architectural workflow of the pipeline, orchestrated using **LangGraph**.

```mermaid
graph TD
    classDef startEnd fill:#e6f4ea,stroke:#137333,stroke-width:2px;
    classDef agent fill:#e8f0fe,stroke:#1a73e8,stroke-width:2px;
    classDef database fill:#fef7e0,stroke:#f9ab00,stroke-width:2px;
    classDef delivery fill:#fce8e6,stroke:#d93025,stroke-width:2px;

    Start([Start Aggregator Pipeline]):::startEnd
    
    subgraph Core Pipeline (LangGraph Orchestrator)
        Collector[Collector Agent]:::agent
        Deduplicator[Deduplicator Agent]:::agent
        Ranker[Ranker Agent]:::agent
        Writer[Writer Agent]:::agent
        Delivery[Delivery Agent]:::delivery
    end

    %% External Components
    RSSSources[(config/rss_sources.yaml)]:::database
    ChromaDB[(ChromaDB Persistent Store)]:::database
    GeminiAPI[Gemini LLM API]:::agent
    Telegram[(Telegram Channel)]:::delivery
    EmailServer[(SMTP Email Server)]:::delivery
    SQLiteStore[(SQLite Checkpointer)]:::database
    LocalFiles[(Local Newsletters Archive)]:::database

    %% Connections
    Start -->|Trigger / cron| Collector
    Collector -->|Reads config| RSSSources
    Collector -->|Fetches, parses & cleans body| Deduplicator
    
    Deduplicator -->|Generates embeddings| ChromaDB
    Deduplicator -->|Queries & stores embeddings| ChromaDB
    Deduplicator -->|Filters duplicates| Ranker
    
    Ranker -->|Scores & filters top articles| Writer
    
    Writer -->|Sends article payload| GeminiAPI
    GeminiAPI -->|Generates newsletter markdown| Writer
    Writer -->|Passes newsletter| Delivery
    
    Delivery -->|Saves markdown/HTML copies| LocalFiles
    Delivery -->|Broadcasts newsletter| Telegram
    Delivery -->|Emails subscribers| EmailServer
    
    Delivery --> End([End Pipeline]):::startEnd

    %% Checkpoint saves
    Collector -.->|Checkpoint state| SQLiteStore
    Deduplicator -.->|Checkpoint state| SQLiteStore
    Ranker -.->|Checkpoint state| SQLiteStore
    Writer -.->|Checkpoint state| SQLiteStore
    Delivery -.->|Checkpoint state| SQLiteStore
```

---

## 2. Technical Stack

The project leverages a modern Python-based AI agent stack:

| Component | Technology | Description |
| :--- | :--- | :--- |
| **Core Framework** | **LangGraph / LangChain** | Coordinates the 5-agent sequential workflow with state-saving and pause/resume capabilities. |
| **LLM Provider** | **Google Gemini (langchain-google-genai)** | Handles newsletter writing and summarization using models like `gemini-3.5-flash`. |
| **RSS Parsing** | **feedparser** | Standard parser used to pull entries from structured XML feeds. |
| **Web Scraping** | **newspaper3k / readability-lxml** | Crawls the full web pages of RSS feeds, extracting and cleaning HTML to isolate the article content. |
| **Vector Database** | **ChromaDB** | Local persistent store used to save article embeddings. |
| **Embeddings** | **sentence-transformers** | Locally generates vector representations of articles to determine semantic similarity. |
| **Delivery Integrations** | **aiosmtplib (SMTP) & Telegram Bot API** | Sends HTML newsletters to email lists and broadcasts markdown newsletters to Telegram. |
| **Checkpointer** | **SQLite (aiosqlite)** | Enables saving run checkpoints, allowing manual pipeline recovery. |

---

## 3. How It Works (Step-by-Step)

The pipeline executes sequentially in 5 stages:

### Step 1: Collector Agent (`src/collector_agent.py`)
- Reads the YAML file `config/rss_sources.yaml` to identify target RSS feeds.
- Fetches RSS XML in parallel and parses links/metadata.
- Scrapes the full content of each article using `readability-lxml` to remove boilerplate headers, footers, and ads, keeping only the actual article text.

### Step 2: Deduplicator Agent (`src/deduplicator_agent.py`)
- Generates vector embeddings for each collected article.
- Computes **cosine similarity** between new articles and previously stored articles in ChromaDB.
- Removes duplicates (similarity index $\ge 0.85$), ensuring readers do not get repeated stories. Stores new unique articles in ChromaDB.

### Step 3: Ranker Agent (`src/ranker_agent.py`)
- Scores unique articles based on user-configured interests (`config/topics_config.yaml`) and importance metrics.
- Prioritizes highly relevant domains and filters out low-scoring or off-topic articles.
- Yields the top articles (maximum 12) for the newsletter write phase.

### Step 4: Writer Agent (`src/writer_agent.py`)
- Converts article details into a compact JSON payload.
- Fits the payload to token budgets using an iterative fallback loop.
- Calls Gemini to draft a structured, professional, and visually engaging markdown newsletter.
- Automatically creates a static fallback text digest if the LLM fails or times out.

### Step 5: Delivery Agent (`src/delivery_agent.py`)
- Saves the markdown and converted HTML newsletters into `outputs/newsletters/`.
- Broadcasts the markdown newsletter directly to the configured Telegram Channel.
- Establishes a secure connection using `aiosmtplib` to email the HTML newsletter to the subscribers list.
