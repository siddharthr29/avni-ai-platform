# Avni AI Platform

AI-powered implementation platform for [Avni](https://avniproject.org) -- the open-source community health and field data collection system.

## Features

- **Chat Assistant** -- Context-aware AI that understands Avni's data model, SRS format, and implementation patterns. Streams responses via SSE with automatic intent classification.
- **Bundle Generation** -- Paste SRS text or provide structured JSON, and the platform generates a complete Avni implementation bundle (concepts, forms, mappings, privileges) ready to upload.
- **Voice Data Capture** -- Speak observations in natural language and the AI maps them to form fields. Supports 11 Indian languages via the Web Speech API.
- **Image Data Extraction** -- Photograph a paper form or register and Claude Vision extracts structured data mapped to your Avni form fields.
- **Rule Generation** -- Describe business rules in English and receive working JavaScript or declarative rule definitions that follow Avni's rule engine patterns.
- **Support Diagnosis** -- Describe an issue and get a structured diagnosis covering common failure modes: sync problems, UUID mismatches, missing form mappings, and privilege gaps.
- **Knowledge Search** -- Search across 4,949 concepts, 132 rule templates, and 280 form patterns drawn from 5 production organisations.

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- An [Anthropic API key](https://console.anthropic.com/)

### Environment Setup

```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

### Development (two terminals)

**Terminal 1 -- Backend:**

```bash
cd backend
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python run.py
```

The API server starts at http://localhost:8080. Interactive docs are available at http://localhost:8080/docs.

**Terminal 2 -- Frontend:**

```bash
cd frontend
npm install
npm run dev
```

The frontend dev server starts at http://localhost:5173 with hot module replacement. API requests are proxied to the backend automatically.

**Open your browser** at http://localhost:5173.

### Docker (single command)

```bash
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY

docker compose up --build
```

The application is available at http://localhost:80. The frontend nginx container proxies `/api/*` requests to the backend.

### Using Make

```bash
make setup        # Install backend + frontend dependencies
make dev           # Start both backend and frontend
make build         # Build frontend for production
make docker-up     # Start via Docker Compose
make docker-down   # Stop Docker containers
make clean         # Remove build artifacts
```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | -- | Anthropic API key for Claude |
| `AVNI_BASE_URL` | No | `https://staging.avniproject.org` | Avni server URL for sync operations |
| `AVNI_AUTH_TOKEN` | No | -- | Auth token for Avni API calls |
| `CLAUDE_MODEL` | No | `claude-sonnet-4-20250514` | Claude model to use |
| `MAX_TOKENS` | No | `4096` | Maximum tokens per Claude response |
| `BUNDLE_OUTPUT_DIR` | No | `/tmp/avni_bundles` | Directory for generated bundle zip files |
| `VITE_API_URL` | No | `http://localhost:8080` | Backend URL (frontend, dev only) |

## Architecture

```
avni-ai-platform/
  backend/                  FastAPI Python application
    app/
      main.py               App entry point, CORS, router registration
      config.py             Environment-based settings
      routers/              API route handlers
        chat.py             SSE streaming chat with intent classification
        bundle.py           Bundle generation from SRS data/text
        voice.py            Voice transcript to form field mapping
        image.py            Image to form field extraction (Claude Vision)
        knowledge.py        Knowledge base search
        support.py          Support issue diagnosis
        sync.py             Avni API sync (save observations, fetch forms)
      services/             Business logic
        claude_client.py    Anthropic Claude API wrapper
        intent_router.py    Intent classification (8 intent types)
        bundle_generator.py Bundle generation engine
        srs_parser.py       SRS text parsing via Claude
        voice_mapper.py     Voice transcript mapping
        image_extractor.py  Image data extraction
        rule_generator.py   Rule generation from English descriptions
        support_diagnosis.py Issue diagnosis (7 patterns)
        knowledge_base.py   In-memory knowledge search (keyword + fuzzy)
        avni_sync.py        Avni API sync operations
      models/
        schemas.py          Pydantic request/response models
      knowledge/
        data/               Concept patterns, rule templates, form patterns
  frontend/                 React + Vite + TypeScript application
    src/
      App.tsx               Root component with sidebar, header, chat layout
      components/
        Chat.tsx            Chat message list with auto-scroll
        ChatInput.tsx       Message input with attachment support
        ChatMessage.tsx     Message rendering with markdown and code blocks
        Sidebar.tsx         Session list and quick actions
        Header.tsx          Top navigation bar
        BundlePreview.tsx   Bundle generation progress and download
        VoiceCapture.tsx    Voice recording and transcript display
        ImageUpload.tsx     Image upload and extraction results
        FieldMapping.tsx    Mapped field display with confidence scores
        FormContext.tsx     Form context provider for voice/image mapping
        RuleDisplay.tsx     Rule output rendering
        Toast.tsx           Notification toasts
      hooks/
        useChat.ts          Chat state management and SSE streaming
        useVoice.ts         Web Speech API voice capture hook
      services/             API client functions
      types/                TypeScript type definitions
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Service health check |
| `GET` | `/api/health` | API health check with config details |
| `POST` | `/api/chat` | Chat with SSE streaming (intent-aware) |
| `POST` | `/api/bundle/generate` | Start bundle generation from SRS data or text |
| `GET` | `/api/bundle/{id}/status` | Poll bundle generation progress |
| `GET` | `/api/bundle/{id}/download` | Download completed bundle zip |
| `POST` | `/api/voice/map` | Map voice transcript to form fields |
| `POST` | `/api/image/extract` | Extract form data from an image |
| `POST` | `/api/knowledge/search` | Search the Avni knowledge base |
| `POST` | `/api/support/diagnose` | Diagnose a common Avni issue |
| `POST` | `/api/avni/save-observations` | Save mapped data to Avni |
| `GET` | `/api/avni/form/{uuid}` | Fetch an Avni form definition |
| `GET` | `/api/avni/subjects/search` | Search Avni subjects by name |

## Tech Stack

- **Frontend:** React 19, Vite 7, TypeScript 5.9, Tailwind CSS v4, Lucide icons
- **Backend:** FastAPI, Python 3.12, Uvicorn, Pydantic v2
- **AI:** Claude Sonnet (Anthropic) for chat, rules, and vision; Web Speech API for voice
- **Deployment:** Docker Compose, Nginx (reverse proxy + static serving)

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes and ensure both backend and frontend start without errors
4. Run the frontend linter: `cd frontend && npm run lint`
5. Commit your changes with a descriptive message
6. Push to your fork and open a pull request

## License

MIT
