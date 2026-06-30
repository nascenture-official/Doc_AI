# Django DocChat — AI-Powered Document Chat Platform

A web application built with Django that allows users to upload PDF files and have intelligent AI-powered conversations with their content. The application uses a full Retrieval-Augmented Generation (RAG) pipeline powered by **Pinecone hybrid search** (dense + sparse BM25 vectors) and OpenAI, with a clean, responsive interface and real-time streaming responses. Background tasks are powered by **Celery** with **Upstash Redis** as the broker.

## Features

### Document Chat & Intelligence
- Retrieval-Augmented Generation (RAG) powered chat grounded in document content
- Hybrid search combining dense semantic vectors (OpenAI) and sparse BM25 keyword vectors (Pinecone)
- Page-level source citations for every AI response
- Real-time response streaming via Server-Sent Events (SSE)
- Abort generation — stop an in-progress AI response mid-stream
- Smart intent classification — small-talk messages bypass the vector store entirely
- Export chat conversations in multiple formats (PDF, Markdown, TXT)

### Document Search (No AI)
- Keyword search — pure BM25 sparse vector matching across all documents
- Phrase search — exact phrase matching with BM25 candidate retrieval + post-filter
- No LLM involved — direct vector store results only

### AI Document Actions
- On-demand AI document summarization (concise and detailed)
- Extract key points from documents
- Generate custom FAQs based on document content
- Rewrite document sections into multiple distinct styles
- Translate documents into various languages

### Interactive Reader & Annotations
- Fully responsive, built-in PDF document reader
- Color-coded text highlighting directly on PDFs
- Attach custom notes to highlights and pages
- Bookmark important pages for quick access
- Integrated search functionality for notes and annotations

### PDF Comparison
- Side-by-side comparison tool for multiple PDF versions
- Automatically detect and highlight added, removed, and modified sections

### Team Collaboration
- Shared workspaces with Owner / Admin / Member roles
- Email-based workspace invitations with accept/decline links
- Ad-hoc per-document sharing (view or edit) independent of workspace membership
- Centralized permission checks govern document/folder visibility across documents, chat, and search

### Management & Platform
- User authentication with email verification and Google OAuth
- PDF upload with real-time background processing status
- Automatic OCR fallback (RapidOCR) for scanned/image-only PDF pages
- Arbitrary nested folder organization for document management
- Conversation history with infinite-scroll message loading
- User dashboard with document stats, storage usage, and recent activity
- Profile management with avatar upload and bio

## Requirements

- Python 3.13+
- Django 6+
- An OpenAI API key
- A Pinecone API key (free tier available at [app.pinecone.io](https://app.pinecone.io))
- An Upstash Redis database (free tier available at [console.upstash.com](https://console.upstash.com)) — used as the Celery broker
- See `requirements.txt` for the complete list of Python dependencies

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd doc-chat
```

### 2. Create and Activate a Virtual Environment

**Windows**

```bash
python -m venv venv
venv\Scripts\activate
```

**macOS/Linux**

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Set Up Upstash Redis (Celery Broker)

The application uses **Celery** for background task processing (PDF ingestion, AI summaries, OCR, etc.) and **Upstash Redis** as the message broker. Upstash offers a serverless Redis with a generous free tier — no local Redis installation required.

#### Step-by-step: Get your Upstash Redis URL and Token

1. **Create an account** — Go to [https://console.upstash.com](https://console.upstash.com) and sign up (free, no credit card required).

2. **Create a Redis database**
   - Click **"Create Database"** in the top-right corner.
   - Give it a name (e.g., `doc-chat-redis`).
   - Select a **region** close to you (e.g., `us-east-1`).
   - Choose **"Global"** replication (optional — the free tier is enough).
   - Click **"Create"**.

3. **Get the REST URL and Token**
   - After creation, your database dashboard opens automatically.
   - Scroll down to the **"REST API"** section (or click the **"Details"** tab).
   - You will see two values:
     - **`UPSTASH_REDIS_REST_URL`** — looks like `https://your-db-name.upstash.io`
     - **`UPSTASH_REDIS_REST_TOKEN`** — a long alphanumeric string

4. **Get the Celery-compatible `rediss://` connection string**
   - In the same dashboard, look for the **"Connect"** section or the **"CLI"** tab.
   - Find the **"Redis URL"** (starts with `rediss://` — note the double `s` for TLS).
   - It looks like: `rediss://default:<your-token>@<your-host>.upstash.io:6379`
   - This is the value you need for `REDIS_URL` in your `.env` file.

   > **Tip:** You can also copy the `rediss://` URL directly from the **"Connect"** → **"Node.js"** or **"Python"** tabs in the Upstash console — it's pre-formatted for you.

5. **Copy all three values into your `.env` file** (see Step 5 below):
   ```env
   UPSTASH_REDIS_REST_URL="https://your-db.upstash.io"
   UPSTASH_REDIS_REST_TOKEN="your-rest-token"
   REDIS_URL="rediss://default:your-token@your-db.upstash.io:6379"
   ```

> **Note:** Upstash uses TLS connections (`rediss://`). The app is already configured in `core/settings.py` to disable certificate verification for Upstash's self-signed cert — no extra configuration needed.

### 5. Configure Environment Variables

Copy the example environment file:

**Windows**

```bash
copy .env.example .env
```

**macOS/Linux**

```bash
cp .env.example .env
```

Generate a Django secret key:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Open your `.env` file and populate all required variables:

```env
SECRET_KEY="your-generated-secret-key"
DEBUG=True

OPENAI_API_KEY="sk-..."

PINECONE_API_KEY="your-pinecone-api-key"
PINECONE_INDEX_NAME="doc-chat-hybrid"
PINECONE_CLOUD="aws"
PINECONE_REGION="us-east-1"

DB_NAME="your-db-name"
DB_USER="your-db-user"
DB_PASSWORD="your-db-password"
DB_HOST="localhost"
DB_PORT="5432"

# Upstash Redis — Celery broker (see Step 4 above)
UPSTASH_REDIS_REST_URL="https://your-db.upstash.io"
UPSTASH_REDIS_REST_TOKEN="your-rest-token"
REDIS_URL="rediss://default:your-token@your-db.upstash.io:6379"

GOOGLE_CLIENT_ID=""
GOOGLE_CLIENT_SECRET=""

EMAIL_HOST_USER="your@gmail.com"
EMAIL_HOST_PASSWORD="your-app-password"
```

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | ✅ | Django's secret key. Keep this private. |
| `DEBUG` | ✅ | Enable/disable Django debug mode. Use `False` in production. |
| `OPENAI_API_KEY` | ✅ | Powers LLM calls (`gpt-4o-mini`) and embeddings (`text-embedding-3-small`). |
| `PINECONE_API_KEY` | ✅ | Pinecone API key — get it from app.pinecone.io. |
| `PINECONE_INDEX_NAME` | ✅ | Pinecone index name. Must use `dotproduct` metric (created by `setup_hybrid_index`). |
| `PINECONE_CLOUD` | ⚠️ Optional | Cloud for index creation (default: `aws`). |
| `PINECONE_REGION` | ⚠️ Optional | Region for index creation (default: `us-east-1`). |
| `REDIS_URL` | ✅ | Full `rediss://` connection string from Upstash — used as the Celery broker. |
| `UPSTASH_REDIS_REST_URL` | ⚠️ Optional | Upstash REST API URL (for direct REST calls if needed). |
| `UPSTASH_REDIS_REST_TOKEN` | ⚠️ Optional | Upstash REST API token. |
| `DB_NAME` | ✅ | PostgreSQL database name. |
| `DB_USER` | ✅ | PostgreSQL database user. |
| `DB_PASSWORD` | ✅ | PostgreSQL database password. |
| `DB_HOST` | ✅ | PostgreSQL host (e.g. `localhost`). |
| `DB_PORT` | ✅ | PostgreSQL port (default: `5432`). |
| `GOOGLE_CLIENT_ID` | ⚠️ Optional | Google OAuth client ID for social login. |
| `GOOGLE_CLIENT_SECRET` | ⚠️ Optional | Google OAuth client secret for social login. |
| `EMAIL_HOST_USER` | ✅ | Gmail address for sending verification emails. |
| `EMAIL_HOST_PASSWORD` | ✅ | Gmail app password (not your regular account password). |

> The `.env` file is excluded from version control and should remain private.

### 6. Run Database Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### 7. Create an Administrator Account

```bash
python manage.py createsuperuser
```

### 8. Set Up Pinecone Index

Run this once to create the Pinecone index with the required `dotproduct` metric:

```bash
python manage.py setup_hybrid_index
```

If you have existing documents already uploaded, re-index them with hybrid vectors:

```bash
python manage.py reindex_hybrid
```

## Running the Application

Three processes must run simultaneously in **separate terminals**. No local vector or cache server is needed — Pinecone is cloud-hosted and Redis is served by Upstash.

```bash
# Terminal 1 — Django development server
python manage.py runserver

# Terminal 2 — Celery worker (required for PDF processing, AI actions, OCR, comparisons)
celery -A core worker --loglevel=info --pool=solo

# Terminal 3 — Celery Flower (optional — task monitoring dashboard at http://localhost:5555)
celery -A core flower
```

Open your browser and visit:

```
http://127.0.0.1:8000/
```

> **Windows note:** Use `--pool=solo` for the Celery worker on Windows. The default `prefork` pool does not work on Windows.

> **Flower dashboard:** Visit `http://localhost:5555` to monitor task queues, retries, and worker status in real time.

## Running Tests

```bash
# Run all tests
python manage.py test

# Run tests for a specific app
python manage.py test accounts
python manage.py test documents
python manage.py test chat
python manage.py test search
python manage.py test teams
```

## Directory Structure

```text
doc-chat/
├── core/           Main Django project configuration, settings, Celery app
├── accounts/       User authentication, profiles, dashboard, Google OAuth
├── documents/      PDF upload, background processing, vector indexing, summaries
├── chat/           Conversations, messages, RAG pipeline, SSE streaming
├── search/         Keyword and phrase search across Pinecone (no LLM)
├── teams/          Shared workspaces, roles, invitations, and document sharing
├── templates/      HTML templates for all apps
├── static/         CSS, JavaScript, and static assets
├── media/          Uploaded PDFs and user avatars
└── embedding_cache/ Locally cached OpenAI embeddings (speeds up re-embeds)
```

## How It Works

### PDF → Vector Pipeline

When a PDF is uploaded, a **Celery background task** extracts its content page-by-page using LangChain's `PyPDFLoader` (in `page` mode). Pages with little or no extractable text (scanned/image-only pages) automatically fall back to RapidOCR. The text is split into overlapping chunks using `RecursiveCharacterTextSplitter`, then each chunk gets **two vector representations** upserted to Pinecone:

```
Upload → Extract (PyPDFLoader + OCR fallback) → Chunk (1200 chars, 250 overlap)
       → Dense embed (text-embedding-3-small) + Sparse encode (BM25)
       → Upsert to Pinecone (dotproduct index)
```

Document status progresses: `uploading` → `processing` → `ready` / `failed`

### RAG Chat Pipeline

Every chat message goes through two phases:

1. **Phase 1** — The user message is saved instantly and a loading placeholder is returned to the UI.
2. **Phase 2** — The message is classified as `SMALLTALK` or `DOCUMENT`. Document questions use `PineconeHybridSearchRetriever` (alpha=0.7, semantic-biased) wrapped in `MultiQueryRetriever` for multi-angle recall. Retrieved context is passed to `gpt-4o-mini` and the response is streamed back token-by-token via SSE.

### Search (No AI)

The search page offers two modes, both using Pinecone directly with no LLM:

- **Keyword mode** — pure BM25 sparse search (alpha=0), ranks chunks by word frequency
- **Phrase mode** — BM25 retrieves 25 candidates, post-filtered for exact phrase occurrence

## Tech Stack

- **Django 6** — web framework
- **Python 3.13+**
- **Bootstrap 5** — UI components
- **PostgreSQL** — primary database
- **Celery** — distributed task queue for background processing
- **Upstash Redis** (`rediss://`) — serverless Redis broker for Celery
- **django-celery-results** — stores Celery task results in PostgreSQL
- **Pinecone** (serverless, hybrid dense+sparse search)
- **pinecone-text** (BM25Encoder for sparse vectors)
- **OpenAI** (`gpt-4o-mini`, `text-embedding-3-small`)
- **LangChain** (`langchain-pinecone`, `langchain-community`, `langchain-openai`)
- **PyPDF / PyMuPDF** (fitz) — PDF text extraction
- **RapidOCR** — scanned-page OCR fallback
- **HTMX** — dynamic UI without full-page reloads
- **django-allauth** — email + Google OAuth authentication

## Demo Video

[Demo video](https://github.com/user-attachments/assets/a42d655d-566e-4118-9e57-db5c5a8f1abd)

## Contributing

Contributions, bug reports, and feature requests are welcome.

To contribute:

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Open a pull request

## License

This project is released under the MIT License.

## About the Maintainer

This project is maintained by Nascenture, a software development company specializing in Django development, custom software solutions, web applications, and cloud-based platforms.

- Django Development Services: https://www.nascenture.com/django-development
- Company Website: https://www.nascenture.com
