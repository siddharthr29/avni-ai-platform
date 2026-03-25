# Avni AI Platform — Master Documentation

> **Version:** 1.0 | **Last Updated:** March 2026 | **Status:** Production

The Avni AI Platform is an AI-powered orchestration layer for the [Avni](https://avni.readme.io/) field data collection platform. It accelerates implementation by translating natural-language requirements into deployable Avni configuration bundles, providing intelligent assistance for form design, rule generation, data extraction, and NGO support.

---

## Table of Contents

1. [Product Overview](#1-product-overview)
2. [Architecture](#2-architecture)
3. [End User Guide](#3-end-user-guide)
4. [Keyboard Shortcuts](#4-keyboard-shortcuts)
5. [API Documentation](#5-api-documentation)
6. [Developer Guide](#6-developer-guide)
7. [Design System](#7-design-system)
8. [Performance](#8-performance)
9. [Security](#9-security)
10. [Monitoring](#10-monitoring)

---

## 1. Product Overview

### What It Does

The Avni AI Platform bridges the gap between field-level data collection requirements and a working Avni application. Implementors describe what they need — in text, voice, images, or structured forms — and the platform generates a complete Avni implementation bundle containing subject types, programs, encounter types, forms, concepts, decision rules, dashboards, and user roles.

The platform covers the full implementation lifecycle:

- **Requirements capture** — structured SRS wizard, free-form chat, voice capture in 11 Indian languages, image extraction from paper registers
- **Specification generation** — AI parses requirements into a complete Software Requirements Specification (SRS) with subject types, programs, encounters, form fields, schedules, dashboards, and roles
- **Bundle generation** — SRS is compiled into a deployable Avni configuration bundle (JSON ZIP)
- **Validation and editing** — bundles are validated against Avni schema rules, with natural-language and structured editing
- **Deployment** — one-click upload to an Avni server, including trial organisation provisioning

### User Personas

The platform is designed for two distinct user personas:

1. **Internal team (Avni domain knowledge)** — Implementors and organisation admins who understand Avni concepts (subject types, programs, encounters, concepts). They use the platform to accelerate their existing workflow, reducing specification time from 1.5-2 days to approximately 0.5 day, and reducing spec-to-app effort by roughly 30%.

2. **Trial users (no Avni knowledge)** — NGO staff, program managers, and external stakeholders who have never used Avni. They describe their data collection needs in plain language, and the platform handles all Avni-specific translation. The SRS wizard and AI auto-fill features are designed specifically for this persona.

### Value Proposition

| Metric | Before Platform | With Platform |
|--------|----------------|---------------|
| Requirements to SRS | 1.5-2 days | ~0.5 day |
| SRS to working app | Baseline effort | ~30% effort reduction |
| Bundle generation time (small SRS) | Manual (hours) | 0.014 seconds |
| Bundle generation time (MCH template) | Manual (hours) | 0.009 seconds |
| Languages supported for voice input | English only | 11 Indian languages |

---

## 2. Architecture

### System Overview

```mermaid
graph TB
    FE["Frontend<br/>React 19 + Vite 7 + Tailwind 4<br/>69 components, SPA via Nginx"]
    FE -->|"HTTP / SSE"| BE

    subgraph BE["FastAPI Backend — 160+ endpoints, 24 routers"]
        direction TB
        R["Routers (24)"]
        S["Services (30+)"]
        M["Models (Pydantic)"]
        MW["Middleware<br/>Metrics → Perms → Security → CORS"]
    end

    BE --> DB["PostgreSQL + pgvector<br/>36K+ RAG chunks<br/>18 tables, 14 collections"]
    BE --> LLM["LLM Providers<br/>OpenAI / Groq / Ollama<br/>Gemini / Anthropic"]
    BE --> AVNI["Avni Server<br/>Bundle Upload<br/>Trial Provisioning"]
    BE --> MCP["MCP Server<br/>20 CRUD tools<br/>Config / Forms / Rules"]
```

### Middleware Stack

Every incoming HTTP request passes through four middleware layers in order:

```mermaid
graph LR
    REQ["Request"] --> M1["1. Metrics"]
    M1 --> M2["2. Permissions"]
    M2 --> M3["3. Security"]
    M3 --> M4["4. CORS"]
    M4 --> RT["Router"]
```

1. **Metrics** (`middleware/metrics.py`) — Records HTTP request latency, status codes, and counts for Prometheus.
2. **Permissions** (`middleware/permissions.py`) — Enforces RBAC. Checks the user's role against the 26-permission matrix. Rejects unauthorized requests with 403.
3. **Security** (`middleware/security.py`) — API key validation, rate limiting, Content Security Policy headers, input sanitisation.
4. **CORS** — Configured origins, allowing the frontend to communicate with the backend in development and production.

### AI Pipeline

The platform operates in two phases, reflecting the implementation lifecycle:

**Phase 1: Requirements to SRS**

```mermaid
graph LR
    UI["User Input<br/>text, voice, image, Excel"] --> IR["Intent Router"]
    IR --> RAG["RAG Retrieval<br/>pgvector + contextual<br/>36K+ chunks"]
    RAG --> LLM["LLM<br/>OpenAI / Groq / Ollama"]
    LLM --> SRS["Structured SRS<br/>Output (JSON)"]
```

**Phase 2: SRS to Deployable Bundle**

```mermaid
graph LR
    SRS["SRS JSON"] --> LLM["LLM Reasoner<br/>60+ field rules<br/>Skip Logic Generator"]
    LLM --> BG["Bundle Generator<br/>ZIP with JSON files"]
    BG --> VAL["Validator<br/>schema + semantic"]
    VAL --> EDIT["Bundle Editor<br/>NL corrections"]
    VAL --> UPLOAD["Upload to<br/>Avni Server"]
    VAL --> DL["Download ZIP"]
```

### Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Frontend | React + TypeScript | 19 |
| Build tool | Vite | 7 |
| CSS | Tailwind CSS | 4 |
| UI components | shadcn/ui (Radix primitives) | Latest |
| Backend | FastAPI (Python) | Latest |
| Database | PostgreSQL + pgvector | 16+ |
| LLM (primary) | Ollama (self-hosted) | Latest |
| LLM (fallback) | Groq Cloud API | Latest |
| LLM (optional) | Anthropic Claude | Latest |
| Embeddings | pgvector HNSW + GIN indexes | -- |
| Monitoring | Prometheus + Grafana | -- |
| Containerisation | Docker Compose | -- |

### Database Schema

The platform uses a single PostgreSQL database (`avni_ai`) with 18 tables across four domains: authentication, chat, knowledge, and operations.

```mermaid
erDiagram
    users ||--o{ sessions : "has"
    users ||--o{ refresh_tokens : "has"
    users ||--o{ user_preferences : "has"
    users ||--o{ saved_prompts : "has"
    sessions ||--o{ messages : "contains"
    sessions ||--o{ feedback : "has"

    users {
        text id PK
        text email
        text name
        text org_name
        text role
        text org_id
        boolean is_active
    }
    sessions {
        text id PK
        text user_id FK
        text title
        text org_id
    }
    messages {
        text id PK
        text session_id FK
        text role
        text content
        jsonb metadata
    }
    feedback {
        text id PK
        text session_id FK
        text message_id FK
        text rating
        text correction
    }
    ai_knowledge_chunks {
        int id PK
        text collection
        text content
        text context_prefix
        vector embedding
        jsonb metadata
        text source_file
    }
    token_usage {
        bigint id PK
        text org_id
        text provider
        text model
        int prompt_tokens
        int completion_tokens
        numeric cost_usd
    }
    audit_log {
        bigint id PK
        text user_id
        text action
        text resource_type
        jsonb details
    }
    bundle_versions {
        text id PK
        text org_id
        text user_id
        text bundle_name
        int version
        text status
        jsonb srs_snapshot
    }
    org_memory {
        text org_id PK
        text org_name
        jsonb subject_types
        jsonb programs
        jsonb encounter_types
        jsonb known_concepts
    }
    ban_lists {
        text id PK
        text org_id
        text word
        text reason
    }
    guardrail_events {
        text id PK
        text user_id
        text event_type
        jsonb details
    }
```

**Table summary:**

| Domain | Tables | Purpose |
|--------|--------|---------|
| Auth | users, refresh_tokens, user_preferences | User accounts, JWT tokens, settings |
| Chat | sessions, messages, feedback, saved_prompts | Conversation history and ratings |
| Knowledge | ai_knowledge_chunks, document_indexes, org_memory | RAG vectors, org context |
| Operations | bundle_versions, bundle_locks, token_usage, audit_log, ban_lists, guardrail_events, org_budgets | Bundles, costs, compliance |
| System | schema_migrations | Migration tracking |

---

## 3. End User Guide

### 3.1 Chat Interface

The chat interface is the primary interaction surface for the platform. It supports free-form conversation with the AI assistant, which has full knowledge of Avni's domain.

**Sending a message:**
1. Click the chat input area at the bottom of the screen, or press `Ctrl+K` / `Cmd+K` to focus it.
2. Type your message. Use `Shift+Enter` to add a new line without sending.
3. Press `Enter` or click the send button to submit.
4. The AI response streams in real-time via Server-Sent Events (SSE). You will see tokens appear progressively.

**Attaching files:**
1. Click the attachment icon next to the chat input.
2. Select a file (supported: Excel `.xlsx`, PDF, plain text, images).
3. The file is uploaded and the AI processes it in the context of your conversation.

**Using voice:**
1. Click the microphone icon in the chat input area.
2. Speak your message in any of the 11 supported languages.
3. The audio is transcribed and sent as a chat message.

**Session management:**
- Press `Ctrl+N` / `Cmd+N` to start a new chat session.
- Previous sessions are listed in the left sidebar. Click any session to resume it.
- Sessions can be renamed by clicking the session title.
- Sessions can be deleted from the session list.

### 3.2 SRS Wizard

The SRS (Software Requirements Specification) Wizard is a 10-step guided form that walks users through every aspect of an Avni implementation.

**Step 1: Organisation Details**
- Enter the organisation name, description, and program focus area.
- Select the geographic scope (district, state, national).

**Step 2: Subject Types**
- Define the entities your program tracks (e.g., Individual, Household, Village).
- For each subject type, specify registration form fields (name, age, gender, location, etc.).

**Step 3: Programs**
- Create programs that subjects can be enrolled in (e.g., Maternal Health, Nutrition Support).
- Specify enrolment criteria and enrolment form fields.

**Step 4: Encounters**
- Define encounter types within each program (e.g., ANC Visit, Growth Monitoring).
- Specify whether encounters are scheduled or on-demand.

**Step 5: Form Fields**
- For each form (registration, enrolment, encounter), define the data fields.
- Field types: text, numeric, date, single-select coded, multi-select coded, notes, image, ID, location, phone number.
- Mark fields as mandatory or optional.

**Step 6: Schedules**
- Configure visit schedules (e.g., ANC visits at 12, 20, 28, 34, 36, 38, 40 weeks).
- Specify schedule rules and conditions.

**Step 7: Dashboards**
- Define dashboard cards for field workers and supervisors.
- Specify filters (by location, date range, status).

**Step 8: Roles**
- Define user roles (e.g., field worker, supervisor, data manager).
- Assign access permissions per role.

**Step 9: Review**
- Review the complete SRS before generation.
- AI highlights potential issues or missing fields.

**Step 10: Generate**
- Click "Generate Bundle" to produce the Avni configuration.
- Download the ZIP or upload directly to an Avni server.

**AI Auto-Fill:**
At any step, click the "AI Auto-Fill" button to have Claude analyse the existing fields and suggest values for empty ones. This is especially useful for trial users who may not know what fields are standard for a given domain.

### 3.3 Bundle Generation

Bundles can be generated from three input types:

**From SRS Wizard:**
1. Complete the 10-step wizard.
2. Click "Generate Bundle" on the final step.
3. The bundle is generated and displayed in the review interface.

**From Excel/PDF/Text upload:**
1. Navigate to the bundle generation page.
2. Upload an Excel spreadsheet, PDF document, or plain text file containing your requirements.
3. The AI parses the document, extracting subject types, programs, encounters, and fields.
4. Review the parsed SRS in the wizard interface.
5. Make corrections if needed, then generate the bundle.

**From chat:**
1. In the chat interface, describe your data collection needs.
2. The AI generates an SRS and asks for confirmation.
3. Once confirmed, the bundle is generated automatically.

### 3.4 Bundle Review

After generation, the bundle review interface has three tabs:

**Overview Tab:**
- Summary of what was generated: number of subject types, programs, encounters, forms, concepts, and rules.
- Visual hierarchy showing the relationship between entities.

**Files Tab:**
- Lists every JSON file in the bundle.
- Click any file to view its contents with syntax highlighting.
- Files include: subjects, programs, encounter types, forms, concepts, form mappings, decision rules, dashboard configurations, and user groups.

**Validation Tab:**
- Shows validation results categorised as errors (must fix), warnings (should fix), and info (suggestions).
- Common validations: missing mandatory concepts, circular references, invalid coded values, orphaned form elements.
- Click any validation item to jump to the relevant file and line.

**Editing:**
- Use the natural-language editor to describe corrections in plain English (e.g., "Add a BP field to the ANC visit form").
- Use the structured editor for precise JSON-level changes.
- After editing, the bundle is re-validated automatically.

### 3.5 Voice Capture

Voice capture enables users to dictate requirements in their native language.

**Supported languages:**
- English
- Hindi
- Marathi
- Odia
- Tamil
- Telugu
- Kannada
- Bengali
- Gujarati
- Punjabi
- Malayalam

**How to use:**
1. Click the microphone icon in the chat input or SRS wizard.
2. Grant microphone permission if prompted by the browser.
3. Speak clearly. The platform uses the browser's speech recognition API.
4. The transcribed text appears in the input field.
5. Review the transcription, edit if needed, then submit.

The voice mapper service (`POST /api/voice/map`) maps vernacular health terms to standard Avni concepts. For example, "blood pressure" spoken in Hindi is mapped to the corresponding Avni coded concept.

### 3.6 Image Extraction

Image extraction processes photographs of paper registers, tally sheets, and forms.

**How to use:**
1. Navigate to the image extraction feature or use the attachment button in chat.
2. Upload a photograph of a paper register or form.
3. The AI analyses the image, identifying rows, columns, headers, and data.
4. Extracted tabular data is presented in a structured format.
5. Review and confirm the extracted data.
6. The data can be used to auto-populate SRS fields or generate form definitions.

### 3.7 Knowledge Search

The platform maintains a RAG (Retrieval-Augmented Generation) knowledge base with 36,790+ chunks across 14 collections.

**How to use:**
1. In the chat interface, ask any question about Avni (e.g., "How do visit schedules work?" or "What is a program encounter?").
2. The platform searches across all 14 knowledge collections using hybrid search (semantic embeddings + keyword matching).
3. Relevant chunks are retrieved and provided as context to the LLM.
4. The AI response cites the source documents.

**Collections include:** Avni documentation, implementation guides, form design patterns, concept dictionaries, rule templates, video transcripts, bundle generation guides, and UUID registries.

### 3.8 Templates

Five domain-specific templates provide pre-built SRS configurations:

| Domain | Description | Key Forms |
|--------|-------------|-----------|
| **MCH** (Maternal & Child Health) | ANC, PNC, child growth monitoring, immunisation | ANC registration, ANC visit, delivery, PNC visit, child growth monitoring |
| **Nutrition** | Growth monitoring, supplementary feeding, SAM/MAM tracking | Growth monitoring, nutrition assessment, MUAC measurement, supplementary feeding |
| **WASH** (Water, Sanitation & Hygiene) | Water source mapping, sanitation coverage, hygiene practices | Water source survey, household sanitation, community hygiene assessment |
| **Education** | Student tracking, attendance, learning outcomes | Student registration, attendance, learning assessment, school infrastructure |
| **Livelihoods** | SHG management, livelihood tracking, skill training | SHG registration, livelihood assessment, skill training tracking, income monitoring |

**How to use:**
1. Navigate to the Templates page.
2. Browse or search templates by domain.
3. Click "Preview" to see the full SRS before applying.
4. Click "Apply" to load the template into the SRS wizard.
5. Customise the template to match your specific needs.
6. Generate the bundle from the customised SRS.

### 3.9 AI Auto-Fill

AI Auto-Fill uses Claude to intelligently suggest values for empty fields in the SRS wizard.

**How it works:**
1. Fill in what you know (e.g., organisation name, program type, a few subject fields).
2. Click the "AI Auto-Fill" button.
3. The AI analyses the context (domain, existing fields, common patterns) and suggests values for all empty fields.
4. Suggestions appear highlighted. Review each one and accept or reject.

This feature is powered by the LLM Reasoner, which applies 60+ field rules to ensure generated values are semantically valid and follow Avni conventions.

### 3.10 Trial Org Provisioning

One-click trial provisioning creates a complete working Avni environment.

**How to use:**
1. Generate and validate a bundle.
2. Click "Provision Trial Organisation."
3. The platform automatically:
   - Creates a new organisation on the Avni server.
   - Uploads the generated bundle.
   - Creates a user account with credentials.
4. You receive the organisation URL and login credentials.
5. Log in to the Avni field app or web console to see your implementation live.

---

## 4. Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+K` / `Cmd+K` | Focus chat input |
| `Ctrl+N` / `Cmd+N` | New chat session |
| `Escape` | Close mobile sidebar |
| `Enter` | Send message |
| `Shift+Enter` | New line in message |

---

## 5. API Documentation

The backend exposes 110 API endpoints across 24 router groups. All endpoints are prefixed with `/api/` unless otherwise noted. Authentication is via API key header unless the server is running in development mode.

### 5.1 Chat

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/api/chat` | Send a chat message and receive an SSE streaming response. The request body includes the message text, session ID, and optional file attachments. The response is a stream of `text/event-stream` events containing AI-generated tokens. | Yes |

**Request body:**
```json
{
  "message": "How do I create a visit schedule?",
  "session_id": "uuid",
  "attachments": []
}
```

**Response:** SSE stream with `data: {"token": "..."}` events, terminated by `data: [DONE]`.

### 5.2 Bundle

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/api/bundle/generate` | Generate an Avni bundle from a structured SRS JSON object. Returns a bundle ID and status. | Yes |
| `POST` | `/api/bundle/generate-from-excel` | Generate a bundle from an uploaded Excel file. The file is parsed, an SRS is extracted, and the bundle is generated. | Yes |
| `POST` | `/api/bundle/parse-excel` | Parse an Excel file and return the extracted SRS without generating a bundle. Useful for preview/review. | Yes |
| `POST` | `/api/bundle/ai-autofill` | Accept a partial SRS and return AI-suggested values for empty fields. Uses the LLM Reasoner with 60+ field rules. | Yes |
| `GET` | `/api/bundle/{id}/status` | Get the current generation status of a bundle (pending, generating, completed, failed). | Yes |
| `GET` | `/api/bundle/{id}/download` | Download the generated bundle as a ZIP file containing all Avni configuration JSON files. | Yes |

**Generate request body:**
```json
{
  "srs": {
    "organisation": { "name": "...", "description": "..." },
    "subject_types": [...],
    "programs": [...],
    "encounters": [...],
    "form_fields": [...],
    "schedules": [...],
    "dashboards": [...],
    "roles": [...]
  }
}
```

**Status response:**
```json
{
  "id": "uuid",
  "status": "completed",
  "created_at": "2026-03-10T12:00:00Z",
  "file_count": 15,
  "validation_summary": { "errors": 0, "warnings": 2 }
}
```

### 5.3 Bundle Editor

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/api/bundle/{id}/edit-nl` | Apply a natural-language correction to a bundle (e.g., "Add a weight field to the growth monitoring form"). The AI interprets the instruction and modifies the bundle files. | Yes |
| `POST` | `/api/bundle/{id}/edit-structured` | Apply a structured JSON patch to specific bundle files. For precise, programmatic edits. | Yes |
| `POST` | `/api/bundle/edit/parse` | Parse a natural-language edit instruction and return the structured changes without applying them. For preview before commit. | Yes |

**NL edit request:**
```json
{
  "instruction": "Add blood pressure fields to the ANC visit form",
  "bundle_id": "uuid"
}
```

### 5.4 Bundle Validation

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/api/bundle/validate/{id}` | Run full validation on a bundle. Returns errors, warnings, and info items. Checks Avni schema compliance, concept references, form mappings, and semantic consistency. | Yes |

**Response:**
```json
{
  "valid": false,
  "errors": [{ "file": "forms/ANC_Visit.json", "message": "Referenced concept 'BP Systolic' not found in concepts.json", "line": 42 }],
  "warnings": [{ "file": "programs/MCH.json", "message": "No encounter types defined for program", "line": 5 }],
  "info": [{ "message": "Consider adding dashboard filters for date range" }]
}
```

### 5.5 Avni Organisation

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/api/avni/org/current` | Get details of the currently configured Avni organisation. | Yes |
| `POST` | `/api/avni/bundle/upload` | Upload a generated bundle to the configured Avni server. | Yes |
| `POST` | `/api/avni/bundle/upload-validated` | Upload a bundle only if it passes validation (zero errors). | Yes |
| `POST` | `/api/avni/bundle/compare` | Compare a generated bundle against the current Avni server configuration and return a diff. | Yes |
| `GET` | `/api/avni/bundle/upload/status` | Check the status of an in-progress bundle upload. | Yes |
| `GET` | `/api/avni/templates` | List available domain templates from the Avni server. | Yes |
| `POST` | `/api/avni/templates/apply` | Apply a domain template to the current organisation. | Yes |
| `POST` | `/api/avni/org/create` | Create a new organisation on the Avni server. | Yes |
| `POST` | `/api/avni/user/create` | Create a new user in the Avni organisation. | Yes |
| `POST` | `/api/avni/trial/provision` | One-click trial provisioning: creates org, uploads bundle, creates user, returns credentials. | Yes |

### 5.6 Voice

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/api/voice/map` | Map vernacular health terms to standard Avni concepts. Accepts transcribed text and a source language code. Returns mapped concept names and confidence scores. | Yes |

**Request:**
```json
{
  "text": "blood pressure check karna hai",
  "language": "hi"
}
```

**Response:**
```json
{
  "mappings": [
    { "term": "blood pressure", "concept": "BP Systolic", "confidence": 0.95 },
    { "term": "blood pressure", "concept": "BP Diastolic", "confidence": 0.95 }
  ]
}
```

### 5.7 Image

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/api/image/extract` | Upload an image of a paper register or form. The AI extracts tabular data (rows, columns, headers, values) and returns structured JSON. | Yes |

**Request:** Multipart form data with `file` field (JPEG, PNG).

**Response:**
```json
{
  "headers": ["Name", "Age", "BP", "Weight"],
  "rows": [
    ["Priya", "28", "120/80", "55"],
    ["Sunita", "32", "130/85", "60"]
  ],
  "confidence": 0.87
}
```

### 5.8 Knowledge

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/api/knowledge/search` | Search the RAG knowledge base. Uses hybrid search (semantic + keyword) across 14 collections. Returns ranked chunks with source attribution. | Yes |

**Request:**
```json
{
  "query": "how to configure visit schedules",
  "top_k": 5,
  "collection": null
}
```

**Response:**
```json
{
  "results": [
    {
      "content": "Visit schedules in Avni are configured...",
      "source": "avni_docs/visit_schedules.md",
      "collection": "documentation",
      "score": 0.92
    }
  ]
}
```

### 5.9 Rules

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/api/rules/generate` | Generate JavaScript decision/visit-scheduling rules from a natural-language description. The AI writes Avni-compatible rule functions. | Yes |
| `POST` | `/api/rules/test` | Test a generated rule against sample data. Returns the rule output and any runtime errors. | Yes |

**Generate request:**
```json
{
  "description": "If BMI is below 18.5, flag as underweight and schedule a follow-up in 2 weeks",
  "rule_type": "decision",
  "form_context": { "concepts": ["BMI", "Weight", "Height"] }
}
```

### 5.10 SRS Chat

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/api/srs/chat` | Conversational SRS building. Send a message in the context of SRS construction and receive AI guidance for the current wizard step. | Yes |
| `POST` | `/api/srs/generate` | Generate a complete SRS from a free-text description. The AI structures the text into the 10-step SRS schema. | Yes |
| `POST` | `/api/srs/auto-fill` | Submit a partial SRS and receive AI-suggested values for all empty fields. Uses domain-aware heuristics and the LLM Reasoner. | Yes |

### 5.11 Documents

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/api/documents/upload` | Upload a document (PDF, text, markdown) to be ingested into the RAG knowledge base. The document is chunked, embedded, and stored in pgvector. | Yes |
| `POST` | `/api/documents/search` | Search uploaded documents. Similar to knowledge search but scoped to user-uploaded content. | Yes |
| `GET` | `/api/documents/collections` | List all RAG collections with chunk counts and metadata. | Yes |

### 5.12 Document Extractor

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/api/document/extract` | Extract structured data from an uploaded document (PDF, Excel, image). First phase of the extraction pipeline. | Yes |
| `POST` | `/api/document/map` | Map extracted fields to Avni concepts. Second phase: associates raw extracted data with standard concept names. | Yes |
| `POST` | `/api/document/clarify` | Request clarification on ambiguous extracted fields. The AI asks targeted questions to resolve ambiguity. | Yes |
| `POST` | `/api/document/process` | Run the full extraction pipeline (extract, map, clarify) in a single call. | Yes |

### 5.13 Users

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/api/users/login` | Authenticate a user. Accepts username/API key and returns a session token and user profile including role and permissions. | No |
| `GET` | `/api/users/{id}` | Get a user's profile by ID. | Yes |
| `POST` | `/api/sessions` | Create a new chat session for the authenticated user. Returns a session ID. | Yes |
| `GET` | `/api/users/{id}/sessions` | List all chat sessions for a user, ordered by last activity. | Yes |
| `GET` | `/api/sessions/{id}/messages` | Get all messages in a chat session. Messages are loaded on-demand (lazy loading). | Yes |
| `PATCH` | `/api/sessions/{id}` | Update session metadata (rename, pin, archive). | Yes |
| `DELETE` | `/api/sessions/{id}` | Delete a chat session and all its messages. | Yes |

### 5.14 Feedback

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/api/feedback` | Submit feedback (thumbs up/down, text comment) on an AI response. Linked to a specific message ID. | Yes |
| `GET` | `/api/feedback/stats` | Get aggregated feedback statistics (total, positive, negative, by feature, over time). | Yes |

### 5.15 Templates

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/api/templates` | List all available domain templates with metadata (name, domain, description, field count). | Yes |
| `GET` | `/api/templates/{domain}` | Get the full template for a specific domain (MCH, Nutrition, WASH, Education, Livelihoods). | Yes |
| `POST` | `/api/templates/preview` | Preview a template applied to a specific organisation context without committing. | Yes |

### 5.16 Usage Tracking

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/api/usage/stats` | Get usage statistics: total chats, bundles generated, documents processed, active users, by time period. | Yes |
| `GET` | `/api/usage/tokens` | Get LLM token usage: total tokens consumed, breakdown by model (Ollama/Groq/Anthropic), cost estimates. | Yes |

### 5.17 Audit

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/api/audit/log` | Query the audit log. Supports filtering by user, action type, resource, date range. Returns paginated results. | Yes |
| `GET` | `/api/audit/bundle-versions` | List all versions of a bundle, including diffs between versions. Tracks every edit and regeneration. | Yes |
| `POST` | `/api/audit/token-budget` | Set or update the LLM token budget for an organisation. When the budget is exhausted, LLM calls are blocked. | Yes |

### 5.18 Preferences

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/api/me/preferences` | Get the authenticated user's preferences (theme, language, default model, notification settings). | Yes |
| `PUT` | `/api/me/preferences` | Update user preferences. | Yes |
| `GET` | `/api/me/custom-instructions` | Get the user's custom instructions for the AI (e.g., "Always use Hindi field labels"). | Yes |
| `PUT` | `/api/me/custom-instructions` | Update custom instructions. | Yes |
| `GET` | `/api/me/saved-prompts` | List the user's saved prompt templates. | Yes |
| `POST` | `/api/me/saved-prompts` | Save a new prompt template. | Yes |
| `DELETE` | `/api/me/saved-prompts/{id}` | Delete a saved prompt. | Yes |
| `GET` | `/api/me/suggested-prompts` | Get AI-generated prompt suggestions based on the user's role and recent activity. | Yes |
| `GET` | `/api/me/org-memory` | Get the organisation's shared memory (key facts, decisions, conventions stored across sessions). | Yes |
| `POST` | `/api/me/org-memory` | Add an entry to organisation memory. | Yes |
| `GET` | `/api/me/chat/search` | Full-text search across all of the user's chat messages. | Yes |
| `GET` | `/api/me/chat/export` | Export all chat sessions as JSON or CSV. | Yes |

### 5.19 Support

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/api/support/diagnose` | Run a quick diagnosis on the user's Avni setup. Checks for common configuration issues and returns findings. | Yes |
| `GET` | `/api/support/troubleshoot/{flow}` | Get a troubleshooting flow by name. Returns the flow's steps, questions, and decision tree. 7 flows available. | Yes |
| `POST` | `/api/support/troubleshoot/{flow}/step` | Submit an answer to a troubleshooting step and receive the next step or resolution. | Yes |
| `GET` | `/api/support/faq` | List all FAQs. Returns 40+ entries grouped by category. | Yes |
| `GET` | `/api/support/faq/{category}` | Get FAQs for a specific category. | Yes |

### 5.20 NGO Support Chat

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/api/support-chat/message` | Send a support message. The AI responds with Avni-specific troubleshooting guidance, drawing from FAQs, troubleshoot flows, and the knowledge base. | Yes |

### 5.21 Sync

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/api/sync/subjects` | Sync subject records from Avni. Used for data analysis and AI-powered insights. | Yes |
| `POST` | `/api/sync/encounters` | Sync encounter records from Avni. | Yes |
| `POST` | `/api/sync/program-enrolments` | Sync program enrolment records from Avni. | Yes |
| `POST` | `/api/sync/program-encounters` | Sync program encounter records from Avni. | Yes |
| `POST` | `/api/sync/save-observations` | Push observation data back to Avni. | Yes |
| `GET` | `/api/sync/form-definition` | Fetch a form definition from Avni by form UUID. | Yes |
| `GET` | `/api/sync/search-subjects` | Search subjects on the Avni server by name, ID, or custom fields. | Yes |

### 5.22 MCP (Model Context Protocol)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/api/mcp/call` | Invoke an MCP tool by name with arguments. The MCP server exposes 20 tools for config analysis, form generation, rule generation, and more. | Yes |
| `GET` | `/api/mcp/tools` | List all available MCP tools with their names, descriptions, and parameter schemas. | Yes |
| `POST` | `/api/mcp/process-config` | Process an Avni configuration through the MCP pipeline. Analyses the config and returns suggestions. | Yes |

### 5.23 Agent

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/api/agent/task` | Submit a complex multi-step task to the ReAct agent. The agent plans and executes steps using available tools. Returns a task ID. | Yes |
| `GET` | `/api/agent/task/{id}` | Get the status and results of an agent task. Includes the step-by-step execution trace. | Yes |
| `POST` | `/api/agent/task/{id}/cancel` | Cancel a running agent task. | Yes |

### 5.24 Health

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/health` | Basic health check. Returns `{"status": "ok"}` if the server is running. | No |
| `GET` | `/api/health` | Detailed health check with dependency status. Reports on PostgreSQL, pgvector, Ollama, Groq, and Avni server connectivity. | No |

**Response:**
```json
{
  "status": "healthy",
  "dependencies": {
    "postgresql": "connected",
    "pgvector": "available",
    "ollama": "connected",
    "groq": "available",
    "avni_server": "connected"
  },
  "uptime_seconds": 86400,
  "version": "1.0.0"
}
```

---

## 6. Developer Guide

### 6.1 Project Structure

```
avni-ai-platform/
├── backend/
│   ├── app/
│   │   ├── __init__.py                  # App package init
│   │   ├── main.py                      # FastAPI app creation, router registration, middleware setup
│   │   ├── config.py                    # Environment configuration (LLM URLs, DB, API keys)
│   │   ├── db.py                        # PostgreSQL connection pool and query helpers
│   │   ├── db_migrations.py             # 7 versioned database migrations
│   │   ├── middleware/
│   │   │   ├── __init__.py              # Middleware package
│   │   │   ├── metrics.py              # Prometheus HTTP metrics middleware
│   │   │   ├── permissions.py          # RBAC permission enforcement middleware
│   │   │   └── security.py            # API key auth, rate limiting, CSP headers
│   │   ├── models/
│   │   │   ├── __init__.py              # Models package
│   │   │   ├── schemas.py             # Pydantic request/response models
│   │   │   └── roles.py               # Role definitions (4 roles, 26 permissions)
│   │   ├── routers/
│   │   │   ├── __init__.py              # Router package
│   │   │   ├── agent.py               # Agent task management endpoints
│   │   │   ├── audit.py               # Audit log and token budget endpoints
│   │   │   ├── avni_org.py            # Avni organisation and bundle upload endpoints
│   │   │   ├── bundle.py              # Bundle generation and download endpoints
│   │   │   ├── bundle_editor.py       # Natural-language and structured bundle editing
│   │   │   ├── bundle_validate.py     # Bundle validation endpoint
│   │   │   ├── chat.py                # SSE chat streaming endpoint
│   │   │   ├── document_extractor.py  # Document extraction pipeline endpoints
│   │   │   ├── documents.py           # Document upload and search endpoints
│   │   │   ├── feedback.py            # User feedback endpoints
│   │   │   ├── image.py               # Image extraction endpoint
│   │   │   ├── knowledge.py           # RAG knowledge search endpoint
│   │   │   ├── mcp.py                 # MCP tool invocation endpoints
│   │   │   ├── preferences.py         # User preferences and personalisation
│   │   │   ├── rules.py               # Rule generation and testing endpoints
│   │   │   ├── srs_chat.py            # SRS conversational building and auto-fill
│   │   │   ├── support.py             # Troubleshooting and FAQ endpoints
│   │   │   ├── support_chat.py        # NGO support chat endpoint
│   │   │   ├── sync.py                # Avni data sync endpoints
│   │   │   ├── templates.py           # Domain template endpoints
│   │   │   ├── usage.py               # Usage and token tracking endpoints
│   │   │   ├── users.py               # Auth, sessions, and user management
│   │   │   └── voice.py               # Voice-to-concept mapping endpoint
│   │   ├── services/
│   │   │   ├── __init__.py              # Services package
│   │   │   ├── audit.py               # Audit logging to database
│   │   │   ├── avni_org_service.py    # Avni server API client (org, bundle, user)
│   │   │   ├── avni_sync.py           # Avni data synchronisation service
│   │   │   ├── bundle_editor.py       # NL and structured bundle editing logic
│   │   │   ├── bundle_generator.py    # SRS-to-bundle compilation
│   │   │   ├── bundle_validator.py    # Schema and semantic validation
│   │   │   ├── bundle_versioning.py   # Bundle version tracking and diffing
│   │   │   ├── claude_client.py       # Anthropic Claude API client
│   │   │   ├── document_extractor.py  # Document parsing and field extraction
│   │   │   ├── error_translator.py    # User-friendly error message translation
│   │   │   ├── faq_service.py         # FAQ retrieval and search (40+ entries)
│   │   │   ├── feedback.py            # Feedback storage and statistics
│   │   │   ├── image_extractor.py     # Image-to-table extraction
│   │   │   ├── intent_router.py       # Chat intent classification and routing
│   │   │   ├── knowledge_base.py      # Knowledge base management
│   │   │   ├── llm_reasoner.py        # LLM Reasoner with 60+ field rules
│   │   │   ├── mcp_client.py          # MCP server client (20 tools)
│   │   │   ├── org_memory.py          # Organisation shared memory persistence
│   │   │   ├── personalization.py     # Custom instructions, saved/suggested prompts
│   │   │   ├── react_agent.py         # ReAct agent for multi-step task execution
│   │   │   ├── rag_augmented_llm.py   # RAG-augmented LLM response generation
│   │   │   ├── rule_generator.py      # JavaScript rule generation for Avni
│   │   │   ├── rule_validator.py      # JS rule security validation
│   │   │   ├── skip_logic_generator.py # Form skip logic generation
│   │   │   ├── srs_parser.py          # Free-text to structured SRS parser
│   │   │   ├── support_diagnosis.py   # Quick diagnosis engine
│   │   │   ├── template_library.py    # Domain template management (5 domains)
│   │   │   ├── token_budget.py        # LLM token budget tracking and enforcement
│   │   │   ├── troubleshoot.py        # 7 troubleshooting flow definitions
│   │   │   ├── voice_mapper.py        # Vernacular term to concept mapping
│   │   │   ├── pageindex_service.py   # Page indexing service
│   │   │   ├── pageindex/             # Page index subsystem
│   │   │   │   ├── config.yaml        # Page index configuration
│   │   │   │   ├── llm_adapter.py     # LLM adapter for page indexing
│   │   │   │   ├── page_index.py      # Core page indexing logic
│   │   │   │   ├── page_index_md.py   # Markdown page indexing
│   │   │   │   └── utils.py           # Page index utilities
│   │   │   └── rag/                   # RAG subsystem
│   │   │       ├── __init__.py        # RAG package
│   │   │       ├── contextual_retrieval.py  # Contextual retrieval with re-ranking
│   │   │       ├── embeddings.py      # Embedding generation (pgvector)
│   │   │       ├── fallback.py        # RAG fallback strategies
│   │   │       ├── ingestion.py       # Document chunking and ingestion
│   │   │       └── vector_store.py    # pgvector store operations
│   │   └── knowledge/
│   │       └── data/                  # Static knowledge files
│   │           ├── INDEX.md           # Knowledge base index
│   │           ├── bundle_generation_guide.json
│   │           ├── concept_patterns.json
│   │           ├── form_patterns.json
│   │           ├── rule_templates.json
│   │           ├── summary.json
│   │           ├── uuid_registry.json
│   │           ├── video1_english.md
│   │           └── video2_english.md
│   ├── tests/                         # 464 automated tests
│   ├── run.py                         # Dev server entry point
│   └── .env.example                   # Environment variable template
├── frontend/
│   ├── src/
│   │   ├── components/                # 69 React components
│   │   ├── assets/
│   │   └── ...
│   ├── public/
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   └── eslint.config.js
├── docker-compose.yml                 # Development compose (backend + DB)
└── docker-compose.prod.yml            # Production compose (8 services)
```

### 6.2 Running Locally

**Prerequisites:**
- Python 3.12+
- Node.js 20+
- PostgreSQL 16+ with pgvector extension
- Ollama (for self-hosted LLM)

**Backend setup:**

```bash
# Clone the repository
cd avni-ai-platform/backend

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment variables
cp .env.example .env
# Edit .env with your database URL, LLM endpoints, API keys

# Run database migrations
python -c "from app.db_migrations import run_migrations; run_migrations()"

# Start the development server
python run.py
# Server starts at http://localhost:8000
```

**Frontend setup:**

```bash
cd avni-ai-platform/frontend

# Install dependencies
npm install

# Start development server
npm run dev
# Frontend starts at http://localhost:5173
```

**Environment variables (`.env`):**

```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/avni_ai

# LLM endpoints (cascade: Ollama → Groq → Anthropic)
OLLAMA_BASE_URL=http://localhost:11434
GROQ_API_KEY=gsk_...
ANTHROPIC_API_KEY=sk-ant-...  # Optional

# Avni server
AVNI_SERVER_URL=https://app.avniproject.org
AVNI_API_KEY=...

# Security
API_KEY=your-api-key-here
CORS_ORIGINS=http://localhost:5173
RATE_LIMIT_RPM=60

# Optional
DEV_MODE=true  # Disables API key requirement
```

### 6.3 Adding a New API Endpoint

1. **Create or edit a router file** in `backend/app/routers/`. If this is a new feature domain, create a new file:

```python
# backend/app/routers/my_feature.py
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/api/my-feature", tags=["My Feature"])

@router.post("/action")
async def my_action(request: MyRequest):
    result = await my_service.do_something(request)
    return {"status": "ok", "data": result}
```

2. **Create a Pydantic model** in `backend/app/models/schemas.py` for the request/response:

```python
class MyRequest(BaseModel):
    field1: str
    field2: int = 10
```

3. **Create or edit a service** in `backend/app/services/` for business logic.

4. **Register the router** in `backend/app/main.py`:

```python
from app.routers import my_feature
app.include_router(my_feature.router)
```

5. **Add tests** in `backend/tests/`.

### 6.4 Adding a New RAG Collection

1. Prepare your documents (PDF, markdown, or plain text).

2. Use the ingestion service:

```python
from app.services.rag.ingestion import ingest_documents

await ingest_documents(
    collection_name="my_collection",
    documents=[
        {"content": "...", "metadata": {"source": "doc1.md"}},
    ],
    chunk_size=500,
    chunk_overlap=50
)
```

3. The ingestion pipeline will:
   - Split documents into chunks (default 500 tokens, 50 token overlap).
   - Generate embeddings using the configured embedding model.
   - Store chunks with embeddings in pgvector.
   - Build HNSW and GIN indexes for hybrid search.

4. The new collection is automatically available via `/api/knowledge/search` and `/api/documents/collections`.

### 6.5 Adding a New Domain Template

1. Create a template JSON file following the SRS schema. Use an existing template (e.g., MCH) as a reference.

2. Register the template in the template library service (`backend/app/services/template_library.py`):

```python
TEMPLATES = {
    # ... existing templates ...
    "my_domain": {
        "name": "My Domain",
        "description": "Template for ...",
        "srs": { ... }  # Full SRS structure
    }
}
```

3. The template will appear in `GET /api/templates` and be available for preview and application.

### 6.6 Testing

The test suite contains 464 automated tests covering all routers, services, and middleware.

```bash
# Run all tests
cd backend
pytest

# Run tests with verbose output
pytest -v

# Run tests for a specific module
pytest tests/test_bundle.py

# Run tests matching a pattern
pytest -k "test_chat"

# Run with coverage report
pytest --cov=app --cov-report=html
```

Tests are organised by module and use pytest fixtures for database setup, mock LLM responses, and test data generation.

### 6.7 Database Migrations

Migrations are managed in `backend/app/db_migrations.py` with 7 versioned migrations. Each migration is idempotent (safe to run multiple times).

**Migrations history:**

| Version | Description |
|---------|-------------|
| 1 | Initial schema: users, sessions, messages tables |
| 2 | Add RAG collections and chunks tables with pgvector |
| 3 | Add bundles and bundle_files tables |
| 4 | Add feedback table |
| 5 | Add audit_log and token_usage tables |
| 6 | Add bundle_versions table for version tracking |
| 7 | Add preferences, custom_instructions, saved_prompts, org_memory tables |

**Running migrations:**

```python
from app.db_migrations import run_migrations
run_migrations()  # Applies all pending migrations
```

Migrations run automatically on application startup.

### 6.8 Docker Deployment

**Development:**

```bash
docker-compose up -d
# Starts: backend, PostgreSQL with pgvector
```

**Production (`docker-compose.prod.yml`):**

The production compose file defines 8 services:

| Service | Description |
|---------|-------------|
| `backend` | FastAPI application (Uvicorn, multiple workers) |
| `frontend` | Nginx serving the React SPA build |
| `postgres` | PostgreSQL 16 with pgvector extension |
| `ollama` | Self-hosted Ollama LLM server |
| `nginx` | Reverse proxy with SSL termination |
| `prometheus` | Metrics collection |
| `grafana` | Monitoring dashboards |
| `backup` | Scheduled PostgreSQL backups |

```bash
# Production deployment
docker-compose -f docker-compose.prod.yml up -d

# With SSL certificates
# Place certs in ./nginx/certs/ before starting
```

---

## 7. Design System

The frontend follows the **UX4G (Indian Government Design System)** design language, adapted for the Avni platform.

### Colour Palette

**Primary colours:**

| Name | Hex | Usage |
|------|-----|-------|
| Primary Blue | `#0d6efd` | Buttons, links, active states, focus rings |
| Success Green | `#198754` | Success messages, validation passed, positive feedback |
| Danger Red | `#dc3545` | Errors, validation failures, destructive actions |
| Warning Yellow | `#ffc107` | Warnings, caution states, pending items |

**Gray scale:**

| Token | Hex | Usage |
|-------|-----|-------|
| Gray 50 | `#f8f9fa` | Page backgrounds, subtle fills |
| Gray 100 | `#f1f3f5` | Card backgrounds, alternate rows |
| Gray 200 | `#e9ecef` | Borders, dividers |
| Gray 300 | `#dee2e6` | Disabled borders |
| Gray 400 | `#ced4da` | Placeholder text |
| Gray 500 | `#adb5bd` | Muted text, icons |
| Gray 600 | `#6c757d` | Secondary text |
| Gray 700 | `#495057` | Body text |
| Gray 800 | `#343a40` | Headings |
| Gray 900 | `#212529` | High-emphasis text |

### Typography

The platform uses a system font stack for optimal rendering across operating systems:

```css
font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
             "Helvetica Neue", Arial, "Noto Sans", sans-serif,
             "Apple Color Emoji", "Segoe UI Emoji";
```

### Border Radius

| Token | Value | Usage |
|-------|-------|-------|
| `sm` | `0.25rem` (4px) | Inputs, small badges |
| `md` | `0.5rem` (8px) | Cards, buttons |
| `lg` | `0.75rem` (12px) | Modals, large cards |
| `xl` | `1rem` (16px) | Feature panels, hero sections |

### Animations

| Name | Description | Usage |
|------|-------------|-------|
| `pulse-ring` | Expanding ring pulse | Microphone recording indicator |
| `typing-dot` | Three bouncing dots | AI typing indicator |
| `slideIn` | Slide from right | Toast notifications |
| `shimmer` | Left-to-right gradient sweep | Loading skeleton placeholders |
| `spin` | 360-degree rotation | Loading spinners |

### Component Library

The frontend uses 11 shadcn/ui components built on Radix UI primitives:

| Component | Description |
|-----------|-------------|
| `Button` | Primary, secondary, outline, ghost, and destructive variants |
| `Card` | Content container with header, body, and footer |
| `Dialog` | Modal dialog with overlay, accessible focus management |
| `Tabs` | Tabbed navigation (used in bundle review: Overview, Files, Validation) |
| `Tooltip` | Hover/focus tooltip for additional context |
| `Badge` | Status indicators (role badges, validation status) |
| `Alert` | Informational, warning, and error banners |
| `Input` | Text input with label, validation, and error states |
| `Textarea` | Auto-expanding multiline input (chat input uses scroll height calculation) |
| `ScrollArea` | Custom scrollbar container (chat message list, file viewer) |
| `Separator` | Horizontal or vertical divider line |

---

## 8. Performance

### Bundle Generation

| Scenario | Time | Details |
|----------|------|---------|
| Small SRS (5-10 fields) | 0.014 seconds | Minimal subject type with registration form |
| MCH template | 0.009 seconds | Pre-compiled template with all forms |
| Large SRS (90+ fields) | < 0.1 seconds | Full implementation with multiple programs |

Bundle generation is compute-bound (JSON compilation), not LLM-bound. The LLM is used during SRS construction, not during the final bundle compilation step.

### Chat Streaming

- **Protocol:** Server-Sent Events (SSE) over HTTP.
- **Latency:** First token appears within 200-500ms (Ollama local) or 300-800ms (Groq cloud).
- **Throughput:** Tokens are streamed as they are generated by the LLM, providing real-time feedback.

### Frontend Optimisations

- **Lazy loading:** Session messages are loaded on-demand when a session is selected, not pre-fetched for all sessions.
- **localStorage caching:** User profile and session state are cached in the browser to avoid redundant API calls on page refresh.
- **Auto-expanding textarea:** The chat input dynamically resizes based on content using scroll height calculation, avoiding fixed-size text areas.
- **Vite 7:** Tree-shaking removes unused code, code splitting separates vendor and application bundles, and hot module replacement (HMR) provides instant feedback during development.

### RAG Performance

- **Indexing:** HNSW (Hierarchical Navigable Small World) indexes on pgvector for approximate nearest neighbour search. GIN indexes for keyword/full-text search.
- **Hybrid search:** Combines semantic similarity (embedding cosine distance) with keyword matching (BM25-style) for higher recall.
- **Chunk count:** 36,790+ chunks across 14 collections.
- **Query latency:** Typical hybrid search returns results in 50-150ms.

---

## 9. Security

### Role-Based Access Control (RBAC)

Four roles with progressively broader permissions:

| Role | Description | Key Permissions |
|------|-------------|-----------------|
| `ngo_user` | Field-level NGO staff | Chat, view templates, basic bundle generation |
| `implementor` | Avni implementation team | All of ngo_user + bundle editing, validation, upload, rule generation |
| `org_admin` | Organisation administrator | All of implementor + user management, audit log, token budgets, org memory |
| `platform_admin` | Platform administrator | All permissions including system configuration, all-org access, migration tools |

**26 permissions** are defined in `models/roles.py` and enforced by `middleware/permissions.py`. Each API endpoint declares its required permission, and the middleware checks the authenticated user's role before allowing access.

### Authentication

- **API key authentication:** Requests must include a valid API key in the `X-API-Key` header or `Authorization: Bearer <key>` header.
- **Development mode:** When `DEV_MODE=true`, API key validation is disabled for local development convenience.
- **Session tokens:** After login, users receive a session token for subsequent requests.

### Rate Limiting

- **In-memory rate limiter:** Configurable requests-per-minute (RPM) per API key.
- **Default:** 60 RPM.
- **Override:** Set `RATE_LIMIT_RPM` in environment variables.
- **Response:** 429 Too Many Requests when limit is exceeded.

### Input Validation

- **Pydantic models:** All request bodies are validated against Pydantic schemas. Invalid requests receive 422 Unprocessable Entity with detailed field-level error messages.
- **File uploads:** File type and size validation on all upload endpoints.

### Content Security Policy

The security middleware adds CSP headers to all responses, restricting script sources, style sources, and frame ancestors.

### CORS

- **Configurable origins:** Set `CORS_ORIGINS` as a comma-separated list of allowed origins.
- **Development default:** `http://localhost:5173` (Vite dev server).
- **Production:** Set to the actual frontend domain.

### JavaScript Rule Validation

The rule validator (`services/rule_validator.py`) performs security checks on AI-generated JavaScript rules before they are included in bundles:
- Blocks `eval()`, `Function()`, and other dynamic code execution.
- Blocks network access (`fetch`, `XMLHttpRequest`).
- Blocks filesystem access.
- Validates that rules only use approved Avni rule APIs.

---

## 10. Monitoring

### Prometheus Metrics

The metrics middleware (`middleware/metrics.py`) exposes the following metrics at the `/metrics` endpoint:

| Metric | Type | Description |
|--------|------|-------------|
| `http_request_duration_seconds` | Histogram | HTTP request latency by method, path, and status code |
| `http_requests_total` | Counter | Total HTTP requests by method, path, and status code |
| `llm_call_duration_seconds` | Histogram | LLM inference latency by model (Ollama/Groq/Anthropic) |
| `llm_calls_total` | Counter | Total LLM calls by model |
| `llm_tokens_total` | Counter | Total LLM tokens consumed by model and direction (input/output) |
| `rag_search_duration_seconds` | Histogram | RAG search latency by collection |
| `rag_searches_total` | Counter | Total RAG searches by collection |
| `bundle_generation_duration_seconds` | Histogram | Bundle generation time |
| `bundle_generations_total` | Counter | Total bundle generations by status (success/failure) |

### Grafana Dashboard

The production deployment includes a pre-configured Grafana dashboard with 11 panels:

| Panel | Visualisation | Description |
|-------|--------------|-------------|
| Request Rate | Time series | HTTP requests per second over time |
| Error Rate | Time series | 4xx and 5xx responses over time |
| Latency P50/P95/P99 | Time series | Request latency percentiles |
| LLM Latency | Time series | LLM call duration by model |
| LLM Token Usage | Bar chart | Token consumption by model over time |
| RAG Search Latency | Time series | Knowledge search response times |
| Bundle Generation | Counter | Total bundles generated (success vs failure) |
| Active Users | Gauge | Currently active users (sessions in last 30 min) |
| Top Endpoints | Table | Most-called API endpoints with avg latency |
| Error Log | Table | Recent 5xx errors with request details |
| System Health | Status map | Dependency health (DB, LLM, Avni server) |

### Health Endpoints

Two health endpoints provide different levels of detail:

- **`GET /health`** — Lightweight check. Returns `{"status": "ok"}` if the FastAPI process is running. Used by load balancers and container orchestrators for liveness probes.

- **`GET /api/health`** — Comprehensive check. Tests connectivity to all dependencies (PostgreSQL, pgvector extension, Ollama, Groq, Avni server) and reports individual status. Used by monitoring systems for readiness probes.

### Structured Logging

The application uses Python's `logging` module with structured JSON output in production. Log entries include:
- Timestamp
- Log level
- Module and function name
- Request ID (for tracing across middleware and services)
- User ID (when authenticated)
- Duration (for timed operations)

Logs are written to stdout for collection by Docker logging drivers or log aggregation systems.

---
