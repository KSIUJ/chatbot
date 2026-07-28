<h1 align="center">Jagiellonian University Faculty Chatbot – Faculty of Mathematics and Computer Science</h1>

<p align="center">
  A RAG-based chatbot answering student and prospective-student questions about the JU Faculty of Mathematics and Computer Science.
  <br>Built by the KSI Student Science Club.
</p>

<p align="center">
    <img src="https://img.shields.io/badge/status-in%20progress-yellow">
    <img src="https://img.shields.io/badge/python-3.11+-blue">
    <img src="https://img.shields.io/badge/license-TODO-lightgrey">
  </p>

<p align="center">🇵🇱 <a href="README.md">Polska wersja / Polish version (main)</a></p>

---

## Table of contents

- [About the project](#about-the-project)
- [Why this project exists](#why-this-project-exists)
- [Architecture](#architecture)
- [Installation](#installation)
- [Usage](#usage)
- [Repository structure](#repository-structure)
- [Team](#team)
- [Roadmap](#roadmap)
- [License](#license)

---

## Language Versions / Wersje językowe

- **English** — this document
- [Polish Version](README.md)

---

## About the project

Built as part of the **KSI Student Science Club (Koło Naukowe Studentów Informatyki)** at the Jagiellonian University Faculty of Mathematics and Computer Science (UJ WMI). The goal of the project is to build a dedicated chatbot using a **Retrieval-Augmented Generation (RAG)** architecture, able to answer Faculty-related questions based on verified documents and source data.

> _The project is under active development. Some features are still being implemented._

**TODO (optional):** some example questions

## Why this project exists

Our project was born out of a need to make life easier for students (especially those just starting out at WMI), and to build a real, advanced engineering tool within the KSI Student Science Club. We wanted to combine theory with practice:

- Use a RAG (Retrieval-Augmented Generation) architecture to search real Faculty databases and websites.
- Build a fully local AI ecosystem (based on, among others, a Qwen model).
- Create a centralized, intelligent assistant that answers questions about courses, credit requirements, or club materials in a few seconds, removing the need to click through dozens of subpages.

## Architecture

The system is built on a modern tech stack for RAG systems:

- **LLM (Decoder):** `Qwen3-30B-A3B Q4_K_M` model, hosted locally.
- **Embeddings / Database:** (TODO: fill in).
- **Document processing:** `pymupdf4llm`, `BeautifulSoup4`, `pypdf`, `python-docx`.
- **Backend:** Python, (TODO: fill in).

## Installation

**TODO:** the project is still under construction, so a full end-to-end install guide doesn't exist yet. Below is a skeleton to fill in as each module is completed.

### Requirements

- Python 3.11+
- **TODO:** remaining requirements

### Steps

```bash
# 1. Clone the repository
git clone <TODO-repo-url>
cd <TODO-repo-name>

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
# TODO: create a single requirements.txt covering the whole project

# 4. Configure environment variables
cp .env.example .env   # TODO: add a .env.example file
# fill in MORDOR_COOKIE, USOS API credentials, etc.
```

## Usage

Once the environment is set up (see [Installation](#installation)):

```bash
# Scrape faculty websites and Wikipedia
python src/data/strony/scraper.py

# Download files from Mordor
python src/data/mordor/files_downloader.py

# Process downloaded Mordor files into chunks
python src/data/mordor/mordor_scraper.py

# Query the USOS API (exploratory/anonymous mode)
python src/data/usos/usos_client.py services/fac/fac2 --params fac_id=WMI

# TODO: fill in as next steps are completed
```

## Repository structure

```
.
├── docs/
│   └── plan.txt              # project plan, sprint notes
├── src/
│   ├── backend/
│   │   └── main.py           # backend API (FastAPI) — in progress
│   └── data/
│       ├── mordor/           # downloading and processing files from Mordor
│       ├── strony/           # scraper for faculty/club websites and Wikipedia
│       └── usos/             # USOS API client
├── README.md
└── README.en.md
```

**TODO:** expand this as more directories are added

## Team

**Mentor:** Oliwier Polak (@Kangurur)

**Team members:**

- **Karol Dziekan** (@Dariooo23)
- **Patrycja Jaworska** (@zazu1023)
- **Sonia Skuczeń** (@SonSku)
- **Mikołaj Suchan** (@Wuchan33)
- **Aleksandra Woźny** (@olkaa566)

## Roadmap

**Must have**

- RAG (encoder + database + decoder)
- Data

**Should have**

- Simple website

**Could have**

- Nicer website
- Advanced features
- User accounts, etc.
- Automation

**TODO:** replace with the current roadmap / link to the project board once the plan evolves.

## License

**TODO:** no license has been chosen yet.
