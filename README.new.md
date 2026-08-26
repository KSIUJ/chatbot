<h1 align="center">Jagiellonian University Faculty Chatbot – Faculty of Mathematics and Computer Science</h1>

<p align="center">
  A RAG-based chatbot answering student and prospective-student questions about the JU Faculty of Mathematics and Computer Science.
  <br>Built by the KSI Student Science Club.
</p>

<p align="center">
    <img src="https://img.shields.io/badge/status-in%20progress-yellow">
    <img src="https://img.shields.io/badge/python-3.10+-blue">
    <img src="https://img.shields.io/badge/license-TODO-lightgrey">
  </p>

<p align="center">
    <img src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white">
    <img src="https://img.shields.io/badge/React-19-149ECA?logo=react&logoColor=white">
    <img src="https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white">
    <img src="https://img.shields.io/badge/SQLAlchemy-D71F00?logo=sqlalchemy&logoColor=white">
    <img src="https://img.shields.io/badge/ChromaDB-vector%20store-6E56CF">
    <img src="https://img.shields.io/badge/Ollama-Qwen2.5-000000?logo=ollama&logoColor=white">
    <img src="https://img.shields.io/badge/Tailwind%20CSS-06B6D4?logo=tailwindcss&logoColor=white">
  </p>

---

## Table of contents

<!-- TODO [Screenshot](#screenshot)-->

- [About the project](#about-the-project)
- [Why this project exists](#why-this-project-exists)
- [Architecture](#architecture)
- [Installation](#installation)
- [Usage](#usage)
- [Repository structure](#repository-structure)
- [Team](#team)
- [License](#license)

---

## About the project

A chatbot for the Jagiellonian University Faculty of Mathematics and Computer Science (UJ WMI), built by the **KSI Student Science Club**. It uses **Retrieval-Augmented Generation (RAG)** to answer Faculty-related questions grounded in real, verified sources instead of guessing.

What it does:

- Answers questions about credit requirements, course rules, and Faculty procedures using documents indexed from Mordor (the Faculty's internal file-sharing platform) and Faculty/club websites.
- Pulls staff contact info, office hours, and positions directly from the USOS API.
- Surfaces the actual source file (including scanned PDFs and images) behind an answer, not just a generated summary.
- Runs entirely on a self-hosted stack — local embeddings and a local LLM served through Ollama, no third-party AI API calls.
<!--TODO: user accounts (registration/login) are in progress"-->

> _The project is under active development. The RAG pipeline and backend API are functional._

<!--## Screenshot

 TODO: dodać screenshot konweracji
<p align="center">
  <img src="docs/screenshot.png" alt="Chatbot UI screenshot placeholder" width="600">
</p> -->

## Why this project exists

Our project was born out of a need to make life easier for students (especially those just starting out at WMI), and to build a real, advanced engineering tool within the KSI Student Science Club. We wanted to combine theory with practice:

- Use a RAG (Retrieval-Augmented Generation) architecture to search real Faculty databases and websites.
- Build a fully local AI ecosystem (served through Ollama, running a Qwen model).
- Create a centralized, intelligent assistant that answers questions about courses, credit requirements, or club materials in a few seconds, removing the need to click through dozens of subpages.

## Architecture

- **LLM (Decoder):** `Qwen2.5:14b`, served locally through [Ollama](https://ollama.com/) (`src/backend/llm/client.py`). Model and host are configurable via `OLLAMA_MODEL` / `OLLAMA_HOST`.
- **Embeddings:** `sentence-transformers`, defaulting to [`sdadas/mmlw-roberta-large`](https://huggingface.co/sdadas/mmlw-roberta-large) — a model tuned for Polish retrieval (`src/backend/RAG/encoder.py`). Swappable via `RAG_EMBEDDING_MODEL` without code changes.
- **Vector store:** [ChromaDB](https://www.trychroma.com/) (`PersistentClient`), storing all three data sources in a single collection distinguished by a `source` field (`src/backend/RAG/vectorstore.py`).
- **Relational database:** SQLAlchemy + Alembic migrations, SQLite by default (configurable via `DATABASE_URL`) — stores users, conversations, and messages (`src/backend/models.py`, `src/backend/database.py`).
- **Backend API:** FastAPI (`src/backend/main.py`), exposing chat and conversation endpoints.
- **Document processing:** `pymupdf4llm`, `BeautifulSoup4`, `pypdf`, `python-docx`.
- **Frontend:** React 19 + TypeScript + Vite + Tailwind CSS (`src/frontend/`).

### Data sources

Three independent ingestion pipelines feed the vector store (`src/backend/RAG/ingest/`), unified under one CLI:

- **Mordor** (`from_mordor.py`) — files downloaded from the Faculty's internal file-sharing platform via `src/data/mordor/files_downloader.py`.
- **Strony** (`from_strony.py`) — a scraper over Faculty/club websites (`src/data/strony/scraper.py`).
- **USOS** (`from_usos.py`) — data pulled through the USOS API (`src/data/usos/`), covering both anonymous and signed/authenticated calls.

## Installation

### Requirements

- Python 3.10+
- Node.js (for the frontend)
- [Ollama](https://ollama.com/) running locally with a chat model pulled (default: `qwen2.5:14b`)

### Steps

```bash
# 1. Clone the repository
git clone git@github.com:KSIUJ/chatbot.git
cd chatbot

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install backend dependencies
pip install -r requirements.txt

# 3a. Install extra dependencies needed only for the strony/mordor scrapers
# (not required if you only run the backend/RAG pipeline)
pip install -r src/data/strony/requirements.txt
pip install -r src/data/mordor/requirements.txt

# 4. Configure environment variables
cp .env.example .env
# fill in USOS_CONSUMER_KEY / USOS_CONSUMER_SECRET if you need signed USOS calls,
# and optionally RAG_EMBEDDING_MODEL / RAG_QUERY_PREFIX / RAG_PASSAGE_PREFIX
#
# The following are NOT in .env.example but can be added manually if needed:
# MORDOR_COOKIE, DATABASE_URL, FRONTEND_ORIGINS, OLLAMA_HOST, OLLAMA_MODEL
# (see defaults in src/backend/config.py, database.py, llm/client.py)

# 5. Apply database migrations
python -m alembic upgrade head

# 6. Install frontend dependencies
cd src/frontend
npm install
```

## Usage

### Backend API

```bash
# from the repo root, with the venv active
uvicorn src.backend.main:app --reload
```

Key endpoints:

- `GET /health` — health check
- `POST /conversations` — start a new conversation
- `GET /conversations/{id}` — fetch a conversation and its message history
- `POST /chat` — send a message (optionally with `conversation_id`), get back the assistant's reply plus matched source files

### Frontend

```bash
cd src/frontend
npm run dev
```

### Data ingestion

```bash
# Scrape faculty/club websites and Wikipedia
python src/data/strony/scraper.py

# Download files from Mordor
python src/data/mordor/files_downloader.py

# Pull data from USOS (exploratory CLI)
python src/data/usos/usos_client.py services/fac/fac2 --params fac_id=WMI

# Ingest all three sources into the vector store
python -m src.backend.RAG.ingest.run_ingest
# or a single source:
python -m src.backend.RAG.ingest.run_ingest --source mordor
```

### Tests

```bash
pytest
```

## Repository structure

```
.
├── alembic/                        # database migrations
├── data/                           # runtime output (gitignored, empty in repo)
├── dataset/                        # runtime vector store output (gitignored, empty in repo)
├── docs/                           # sprint notes
├── src/
│   ├── backend/
│   │   ├── main.py                 # FastAPI app: chat + conversation endpoints
│   │   ├── database.py, models.py  # SQLAlchemy models (users, conversations, messages)
│   │   ├── config.py
│   │   ├── request.py, response.py
│   │   ├── llm/                    # Ollama client + prompt/answer generation
│   │   └── RAG/
│   │       ├── encoder.py          # text -> embeddings
│   │       ├── vectorstore.py      # ChromaDB wrapper
│   │       ├── retriever.py, context_builder.py
│   │       └── ingest/             # per-source loaders (mordor, strony, usos) + CLI
│   ├── data/                       # source code for scraping/downloading (mordor, strony, usos)
│   └── frontend/                   # React + TypeScript + Vite + Tailwind app
├── tests/backend/RAG/              # pytest suite for the RAG pipeline
├── requirements.txt
└── README.md
```

## Team

**Mentor:** Oliwier Polak (@Kangurur)

**Team members:**

- **Karol Dziekan** (@Dariooo23)
- **Patrycja Jaworska** (@zazu1023)
- **Sonia Skuczeń** (@SonSku)
- **Mikołaj Suchan** (@Wuchan33)
- **Aleksandra Woźny** (@olkaa566)

## License

**TODO:** no license has been chosen yet.
