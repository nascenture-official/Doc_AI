# Django DocChat — AI-Powered Document Chat Platform

A web application built with Django that allows users to upload PDF files and have intelligent AI-powered conversations with their content. The application uses a full Retrieval-Augmented Generation (RAG) pipeline powered by ChromaDB and OpenAI, with a clean, responsive interface and real-time streaming responses.

## Features

- User authentication with email verification and Google OAuth
- PDF upload with real-time background processing status
- Arbitrary nested folder organization for document management
- Retrieval-Augmented Generation (RAG) powered chat grounded in document content
- Page-level source citations for every AI response
- Real-time response streaming via Server-Sent Events (SSE)
- Abort generation — stop an in-progress AI response mid-stream
- Smart intent classification — small-talk messages bypass the vector store entirely
- Export chat conversations in multiple formats (PDF, Markdown, TXT)
- On-demand AI document summarization (concise and detailed)
- Keyword search across all documents without LLM involvement
- Conversation history with infinite-scroll message loading
- User dashboard with document stats, storage usage, and recent activity
- Profile management with avatar upload and bio
- Secure per-user data isolation in a shared vector store

## Requirements

- Python 3.13+
- Django 6+
- An OpenAI API key
- See `requirements.txt` for the complete list of dependencies

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

### 4. Configure Environment Variables

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

DB_NAME="your-db-dbname"
DB_USER="your-db-user"
DB_PASSWORD="your-db-password"
DB_HOST="localhost"
DB_PORT="5432"

GOOGLE_CLIENT_ID=""
GOOGLE_CLIENT_SECRET=""

EMAIL_HOST_USER="your@gmail.com"
EMAIL_HOST_PASSWORD="your-app-password"
```

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | ✅ | Django's secret key. Keep this private and never commit it to version control. |
| `DEBUG` | ✅ | Enable or disable Django debug mode. Use `False` in production. |
| `OPENAI_API_KEY` | ✅ | Powers all LLM calls (`gpt-4o-mini`) and embeddings (`text-embedding-3-small`). |
| `DB_NAME` | ✅ | PostgreSQL database name. |
| `DB_USER` | ✅ | PostgreSQL database user. |
| `DB_PASSWORD` | ✅ | PostgreSQL database password. |
| `DB_HOST` | ✅ | PostgreSQL host (e.g. `localhost` or a remote host). |
| `DB_PORT` | ✅ | PostgreSQL port (default: `5432`). |
| `GOOGLE_CLIENT_ID` | ⚠️ Optional | Google OAuth client ID for social login. |
| `GOOGLE_CLIENT_SECRET` | ⚠️ Optional | Google OAuth client secret for social login. |
| `EMAIL_HOST_USER` | ✅ | Gmail address used for sending email verification links. |
| `EMAIL_HOST_PASSWORD` | ✅ | Gmail app password (not your regular account password). |

> The `.env` file is excluded from version control and should remain private.

### 5. Run Database Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### 6. Create an Administrator Account

```bash
python manage.py createsuperuser
```

Follow the prompts to create your administrator account.

## Running the Application

Three processes must run **simultaneously** in separate terminals:

```bash
# Terminal 1 — ChromaDB vector store server (required before starting the app)
chroma run --path ./chroma_db --port 8001

# Terminal 2 — Django development server
python manage.py runserver

# Terminal 3 — Background worker (required for PDF processing and summaries)
python manage.py qcluster
```

Open your browser and visit:

```
http://127.0.0.1:8000/
```

## Running Tests

```bash
# Run all tests
python manage.py test

# Run tests for a specific app
python manage.py test accounts
python manage.py test documents
python manage.py test chat
python manage.py test search
```

## Directory Structure

```text
doc-chat/
├── core/           Main Django project configuration and settings
├── accounts/       User authentication, profiles, dashboard, Google OAuth
├── documents/      PDF upload, background processing, vector indexing, summaries
├── chat/           Conversations, messages, RAG pipeline, SSE streaming
├── search/         Keyword search across the vector store without LLM
├── templates/      HTML templates for all apps
├── static/         CSS, JavaScript, and static assets
├── media/          Uploaded PDFs and user avatars
├── chroma_db/      Persisted ChromaDB vector store data
└── embedding_cache/ Locally cached OpenAI embeddings
```

## How It Works

### PDF → Vector Pipeline

When a PDF is uploaded, a background task extracts its content page-by-page using LangChain's `PyPDFLoader` (in `page` mode), splits the text into overlapping chunks using `RecursiveCharacterTextSplitter`, and stores the resulting embeddings in a ChromaDB collection (served via HTTP on port 8001) with per-document and per-user metadata.

```
Upload → Extract (PyPDFLoader, page mode) → Chunk (800 chars, 150 overlap) → Embed (text-embedding-3-small) → ChromaDB
```

Document status progresses through: `uploading` → `processing` → `ready` / `failed`

### RAG Chat Pipeline

Every chat message goes through two phases:

1. **Phase 1** — The user message is saved instantly and a loading placeholder is returned to the UI.
2. **Phase 2** — The message is classified as `SMALLTALK` or `DOCUMENT`. Document questions trigger a ChromaDB similarity search (top 5 chunks filtered by document), the retrieved context is passed to the LLM, and the response is streamed back token-by-token via Server-Sent Events.

## Example Use Cases

- Research document Q&A and analysis
- Legal and contract document review
- Knowledge base search and extraction
- Internal documentation workflows
- AI and LLM document processing pipelines
- Content archiving and migration
- Academic paper summarization
- PDF content digitization projects

## Tech Stack

- Django 6
- Python 3.13+
- Bootstrap 5
- PostgreSQL
- ChromaDB (HTTP server mode)
- OpenAI (`gpt-4o-mini`, `gpt-5-mini`, `text-embedding-3-small`)
- LangChain
- PyPDF / PyMuPDF / pymupdf4llm
- HTMX
- django-allauth
- django-q2

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
