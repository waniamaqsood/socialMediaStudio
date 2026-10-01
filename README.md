# Social Media Studio

A backend content repurposing and publishing system built with **FastAPI, SQLite, and Ollama**.

The system accepts source content as a URL or Markdown, stores the original post, generates platform-specific variants using `llama3.2:latest`, supports review and approval, schedules approved variants, publishes them through platform adapters, and records every publishing attempt in persistent history.

## Features

* URL and Markdown content ingestion
* Persistent source-post storage in SQLite
* AI-powered LinkedIn and Instagram variant generation
* Ollama with `llama3.2:latest`
* Platform-specific content constraints
* Draft / approved / rejected / published workflow
* Approved-content scheduling
* Durable scheduler job store
* Restart recovery for interrupted scheduler jobs
* Idempotent publishing
* Discord real publishing adapter
* Mock LinkedIn and Mock X adapters
* Persistent publish history
* Environment-based secret configuration
* Automated pytest coverage

---

## Architecture

```text
                         ┌──────────────────┐
                         │   Source Input   │
                         │ URL / Markdown   │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │   Post Storage   │
                         │     SQLite       │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │    Generator     │
                         │ Ollama / Llama   │
                         │   3.2:latest     │
                         └────────┬─────────┘
                                  │
                       ┌──────────┴──────────┐
                       ▼                     ▼
                ┌─────────────┐       ┌─────────────┐
                │  LinkedIn   │       │ Instagram   │
                │   Variant   │       │   Variant   │
                └──────┬──────┘       └──────┬──────┘
                       │                     │
                       └──────────┬──────────┘
                                  ▼
                         ┌──────────────────┐
                         │ Review Workflow  │
                         │ draft/approved/  │
                         │ rejected         │
                         └────────┬─────────┘
                                  │
                           approved only
                                  │
                                  ▼
                         ┌──────────────────┐
                         │    Scheduler     │
                         │ Job Store/Worker │
                         └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │ Publisher Layer  │
                         └────────┬─────────┘
                                  │
                   ┌──────────────┼──────────────┐
                   ▼              ▼              ▼
              ┌─────────┐   ┌─────────┐   ┌────────────┐
              │ Discord │   │ Mock X  │   │    Mock    │
              │  Real   │   │         │   │  LinkedIn  │
              └─────────┘   └─────────┘   └────────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │ Publish History  │
                         │ Results/Errors   │
                         └──────────────────┘
```

### Core components

| Component          | Responsibility                               |
| ------------------ | -------------------------------------------- |
| FastAPI            | HTTP API                                     |
| SQLite             | Persistent application storage               |
| Ingestion service  | URL/Markdown source handling                 |
| Generation service | Ollama-powered variant generation            |
| Variant workflow   | Draft, approval, rejection, publishing state |
| Scheduler          | Stores and processes scheduled jobs          |
| Worker             | Publishes due variants                       |
| Publisher layer    | Platform-independent publishing interface    |
| Discord adapter    | Real publishing integration                  |
| Mock adapters      | Safe testing integrations                    |
| Publish history    | Persistent publishing audit trail            |

---

## Workflow

```text
URL / Markdown
      │
      ▼
Store Post
      │
      ▼
Generate Variants
      │
      ▼
    draft
    /   \
   ▼     ▼
approved rejected
   │
   ▼
schedule
   │
   ▼
worker
   │
   ▼
publish
   │
   ▼
published
   │
   ▼
publish history
```

Only **approved** variants can be scheduled or published.

Publishing does not modify the original source post.

---

## Data Model

### Post

Stores the original source material.

```text
Post
├── id
├── source_url
├── content
├── source_type
└── created_at
```

`source_type` is either:

```text
url
markdown
```

### Variant

Stores a generated platform-specific version.

```text
Variant
├── id
├── post_id
├── platform
├── content
├── status
└── created_at
```

Supported generated platforms:

* LinkedIn
* Instagram

### Schedule

Stores when an approved variant should be published.

```text
Schedule
├── id
├── variant_id
├── platform
├── scheduled_at
├── idempotency_key
├── status
└── attempted_at
```

### Publish History

Stores the outcome of publishing attempts.

```text
PublishHistory
├── id
├── variant_id
├── platform
├── idempotency_key
├── result
├── error_message
└── created_at
```

---

## AI Generation

The generation service uses:

```text
Ollama
└── llama3.2:latest
```

The generator reads the **stored source post** rather than directly regenerating from the original request.

It produces:

```text
Stored Post
     │
     ▼
Ollama
     │
     ├── LinkedIn Variant
     └── Instagram Variant
```

### Platform constraints

**LinkedIn**

* 150–3000 characters
* Maximum 5 hashtags
* Professional, natural style

**Instagram**

* Up to 2200 characters
* Maximum 10 hashtags
* More conversational and engaging style

Length and hashtag limits are validated in application code rather than being left entirely to the LLM.

---

## Review Workflow

Variants begin as:

```text
draft
```

They can then be moved through the review workflow:

```text
draft ──► approved ──► published
   │
   └────► rejected
```

Only approved variants can be scheduled.

An attempt to schedule an unapproved variant is rejected by the API.

Approved content is treated as immutable so that the content reviewed by the user remains the content that is scheduled and published.

---

## Scheduling

The scheduler uses a persistent SQLite job store.

A schedule contains:

* Variant ID
* Platform
* Scheduled time
* Idempotency key
* Processing status
* Attempt timestamp

The worker:

1. Finds due jobs.
2. Marks a job as being processed.
3. Publishes the associated variant.
4. Records the publishing result.
5. Marks the schedule as completed.

On restart, jobs left in a processing state can be recovered and returned to the pending queue.

---

## Idempotent Publishing

Each scheduled publication receives an idempotency key:

```text
variant-{variant_id}:slot-{scheduled_time}
```

Before publishing, the publisher checks whether that key already has a successful publish-history record.

If it does, the publication is not sent again.

This protects against duplicate publication when:

* a worker restarts,
* a job is retried,
* the publishing process is invoked more than once.

---

## Publisher Architecture

Publishing uses a common `SocialPublisher` interface.

```text
                 SocialPublisher
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
      Discord       Mock X      Mock LinkedIn
       Adapter       Adapter        Adapter
```

### Discord

Discord is the real platform integration used by the project.

The webhook URL is loaded from an environment variable.

### Mock adapters

Mock X and Mock LinkedIn provide platform implementations without requiring external platform credentials.

The core publishing service works with the common adapter interface rather than containing platform-specific publishing logic.

---

## Publish History

Every publishing attempt is persisted.

Successful attempts contain:

```text
result = success
```

Failed attempts contain:

```text
result = failed
error_message = <failure details>
```

The API exposes the history through:

```text
GET /publish-history
```

This provides an audit trail for publishing activity.

---

## API Endpoints

### Create a post

```text
POST /posts
```

Accepts URL or Markdown source content.

### Approve a variant

```text
POST /variants/{variant_id}/approve
```

### Edit a variant

```text
PUT /variants/{variant_id}
```

### Reject a variant

```text
POST /variants/{variant_id}/reject
```

### Schedule a variant

```text
POST /variants/{variant_id}/schedule
```

Only approved variants can be scheduled.

### Publish a variant

```text
POST /variants/{variant_id}/publish
```

### View publishing history

```text
GET /publish-history
```

Interactive API documentation is available through FastAPI/Swagger when the server is running:

```text
/docs
```

---

## Project Structure

```text
social-media-studio/
│
├── app/
│   ├── main.py
│   │
│   └── services/
│       ├── database.py
│       ├── generator.py
│       ├── ingestion.py
│       ├── pipeline.py
│       ├── publisher.py
│       ├── schedule.py
│       ├── worker.py
│       │
│       └── adapters/
│           ├── base.py
│           ├── discord.py
│           ├── mock_linkedin.py
│           └── mock_x.py
│
├── tests/
│   ├── test_phase4.py
│   ├── test_phase5_worker.py
│   └── discord_test_phase4.py
│
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
├── EVIDENCE.md
└── content_repurposer.db
```

---

## Setup

### 1. Clone the repository

```powershell
git clone <repository-url>
cd social-media-studio
```

### 2. Create a virtual environment

```powershell
python -m venv .venv
```

### 3. Activate it

```powershell
.\.venv\Scripts\Activate.ps1
```

### 4. Install dependencies

```powershell
pip install -r requirements.txt
```

### 5. Configure environment variables

Create `.env` from `.env.example`:

```powershell
Copy-Item .env.example .env
```

Configure the required Discord webhook:

```text
DISCORD_WEBHOOK_URL=<your-discord-webhook>
```

Secrets are loaded from environment variables and are not stored in application source code.

### 6. Initialize the database

```powershell
python -c "from app.services.database import init_db; init_db(); print('Database ready.')"
```

### 7. Start the API

```powershell
uvicorn app.main:app --reload
```

Open the interactive API documentation at:

```text
http://127.0.0.1:8000/docs
```

---

## Ollama Setup

The application expects Ollama to be running locally with:

```text
llama3.2:latest
```

Verify the model is available:

```powershell
ollama list
```

If required, pull it with:

```powershell
ollama pull llama3.2:latest
```

Start Ollama before using the generation workflow.

---

## Running Tests

Run the complete test suite:

```powershell
pytest -q
```

The Phase 5 implementation has been verified with:

```text
9 passed, 13 warnings
```

The warnings are SQLite/Python datetime adapter deprecation warnings and do not represent test failures.

The test suite covers the Phase 4 publishing behaviour and Phase 5 worker/scheduling behaviour.

---

## Real Discord Integration Test

The project includes a separate Discord integration test.

Because this sends a real message to Discord, it should not be run as part of every test-suite execution.

Use it only when verifying the live Discord webhook configuration.

---

## Security and Secrets

Secrets are supplied through environment variables.

The repository should contain:

```text
.env.example
```

but should not contain the real:

```text
.env
```

The Discord webhook URL must never be committed to source control.

---

## Reliability

The Phase 5 scheduler is designed to survive worker restarts.

The scheduler persists job state in SQLite rather than keeping scheduled jobs only in memory.

If a worker stops while processing jobs, processing jobs can be recovered on restart.

Idempotency checks prevent a previously successful publication from being sent again for the same variant and scheduled slot.

---

## Evidence

Implementation and test evidence for the Phase 5 requirements is documented separately in:

```text
EVIDENCE.md
```

It records:

* ingestion behaviour
* constraint validation
* approval gating
* adapter behaviour
* idempotent publishing
* scheduler recovery
* publish history
* Discord integration
* secret handling
* automated test results

---

## Design Principles

The implementation follows these principles:

1. **Persistent source of truth** — original posts are stored before generation.
2. **Separated variants** — generated platform content is stored independently.
3. **Explicit states** — review and publishing states are represented in the database.
4. **Approval gating** — only approved content enters the scheduling/publishing flow.
5. **Idempotent publishing** — the same scheduled publication is not successfully published twice.
6. **Durable scheduling** — scheduler state survives worker restarts.
7. **Adapter abstraction** — publishing logic is separated from platform-specific implementations.
8. **Traceability** — publishing attempts are recorded in persistent history.
9. **Environment-based secrets** — credentials are kept outside source code.
10. **Automated verification** — core behaviour is covered by pytest.

---

## Phase 5 Status

The implemented system covers the core Phase 5 workflow:

```text
Ingest
  ↓
Store
  ↓
Generate
  ↓
Review
  ↓
Approve
  ↓
Schedule
  ↓
Worker
  ↓
Idempotent Publish
  ↓
Publish History
```

The complete automated test suite currently passes successfully.
