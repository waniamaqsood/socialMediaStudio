# Social Media Studio

A backend content repurposing and publishing system built with **FastAPI, SQLite, and Ollama**.

The system accepts source content as a URL or Markdown, stores the original post, generates platform-specific variants using `llama3.2:latest`, supports review and approval, schedules approved variants, publishes them through platform adapters, and records every publishing attempt in persistent history.

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
└── attempted_at
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

Length and hashtag limits are validated in application code rather than being left entirely to the LLM. If a generated variant breaks a rule, the validation errors are sent back to the model and generation is retried, up to 3 attempts. Tone is requested in the prompt but is not checked by code.

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

Editing a variant with `PUT /variants/{variant_id}` replaces its content and returns it to `draft`, so edited content must be approved again before it can be scheduled or published.

---

## Scheduling

The scheduler uses a persistent SQLite job store.

A schedule contains:

* Variant ID
* Platform
* Scheduled time (stored in UTC)
* Idempotency key
* Processing status (`pending`, `processing`, `completed`)
* Attempt timestamp

The worker (`python run_worker.py`) runs as a separate process and checks for due jobs every 5 seconds:

1. Finds due jobs.
2. Marks a job as being processed.
3. Publishes the associated variant.
4. Records the publishing result.
5. Marks the schedule as completed.

On startup, the worker returns jobs left in `processing` (from an interrupted run) to the pending queue.

Times sent to `POST /variants/{id}/schedule` are converted to UTC. A time without a timezone is treated as UTC.

---

## Idempotent Publishing

Each scheduled publication receives an idempotency key:

```text
variant-{variant_id}:slot-{scheduled_time}
```

Before publishing, the publisher checks whether that key already has a successful publish-history record. If it does, the publication is not sent again and the call returns `already_published`.

This protects against repeated publish calls and worker retries for the same slot. It does **not** make delivery exactly-once: see [Reliability and known limitations](#reliability-and-known-limitations).

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

### Switching adapters

Each platform's adapter is chosen by an environment variable, so a swap changes configuration, not business logic:

```text
PUBLISHER_DISCORD=discord | mock_x | mock_linkedin
PUBLISHER_X=mock_x
PUBLISHER_LINKEDIN=mock_linkedin
```

Defaults: Discord variants use the real Discord adapter; X and LinkedIn variants use their mocks. Only the adapter for the variant being published is created, so the mocks work without a Discord webhook.

Example: to send generated LinkedIn variants to your real Discord channel, set `PUBLISHER_LINKEDIN=discord` and `DISCORD_WEBHOOK_URL` in `.env`.

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
socialMediaStudio/
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
│   ├── conftest.py
│   ├── test_phase4.py
│   ├── test_phase5_worker.py
│   ├── test_schedule_timezone.py
│   └── discord_test_phase4.py
│
├── run_worker.py
├── pytest.ini
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── EVIDENCE.md
└── BUILDLOG.md
```

`content_repurposer.db` is created automatically on first run and is not committed.

---

## Setup

### 1. Clone the repository

```powershell
git clone https://github.com/waniamaqsood/socialMediaStudio.git
cd socialMediaStudio
```

### 2. Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
pip install -r requirements.txt
```

### 4. Configure environment variables

```powershell
Copy-Item .env.example .env
```

Edit `.env`:

```text
DISCORD_WEBHOOK_URL=<your-discord-webhook>
```

The webhook is only needed to publish to Discord. Mock publishing works without it. Secrets are loaded from environment variables and are not stored in source code.

### 5. Start Ollama

See [Ollama Setup](#ollama-setup). Generation needs it; everything else does not.

### 6. Start the API

```powershell
uvicorn app.main:app --reload
```

The SQLite database is created automatically on startup. Interactive API docs: <http://127.0.0.1:8000/docs>

### 7. Start the scheduler worker (second terminal)

```powershell
python run_worker.py
```

Both processes use the same SQLite database. Stop either with `Ctrl+C`. If the worker is stopped mid-batch, restarting it returns interrupted jobs to the queue.

---

## Try it

With the API and worker running (PowerShell; use `curl.exe`, not `curl`):

```powershell
# 1. Ingest and generate variants (needs Ollama)
curl.exe -X POST http://127.0.0.1:8000/posts -H "Content-Type: application/json" -d '{\"source_type\":\"markdown\",\"content\":\"Your blog post text here...\"}'

# 2. Approve a variant (use an id from step 1)
curl.exe -X POST http://127.0.0.1:8000/variants/1/approve

# 3. Schedule it a minute or two ahead (UTC)
curl.exe -X POST http://127.0.0.1:8000/variants/1/schedule -H "Content-Type: application/json" -d '{\"scheduled_at\":\"<UTC time 1-2 minutes from now, e.g. 2026-11-15T09:30:00Z>\"}'

# 4. The worker terminal prints the result when the time arrives. Then:
curl.exe http://127.0.0.1:8000/publish-history
```

Scheduling an unapproved variant returns `409` with an error message. By default a LinkedIn variant is published through the mock adapter; set `PUBLISHER_LINKEDIN=discord` to send it to your Discord channel.

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

```powershell
pytest
```

Each test runs against its own temporary database, so the real `content_repurposer.db` is never touched. The two generation tests need Ollama running (see Ollama Setup above).

Tests that post a **real message to Discord** are marked `integration` and skipped by default. To run them, set `DISCORD_WEBHOOK_URL` in `.env`, then:

```powershell
pytest -m integration
```

The tests cover approval gating, scheduling, idempotent publishing, the worker (including restart behaviour), schedule time zones, and generation with platform constraints.

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

## Reliability and known limitations

**What is protected**

* Calling publish again for the same variant and time slot returns `already_published` and records only one success.
* The same variant cannot be scheduled twice for the same time (database `UNIQUE` idempotency key).
* Unapproved variants cannot be scheduled or published.
* Schedules are stored in SQLite. If the worker stops mid-batch, restarting it returns interrupted jobs to the queue.

**Known limitations**

* **This is not exactly-once delivery.** If the process stops after a message is sent but before the result is recorded, or a request times out after Discord accepted the message, a retry can send a second message. Discord webhooks have no idempotency support of their own.
* The duplicate check reads and then writes in application code, so two simultaneous publish calls for the same variant could both send.
* A failed publish leaves its job in `processing` until the worker is restarted. There is no automatic retry or backoff.
* Publish history records the result of each attempt but not a link to the Discord message.
* LinkedIn and X are mock adapters. Discord is the only real integration.
* Instagram variants are generated, but there is no Instagram publisher.
* Length and hashtag limits are enforced in code. Tone is requested in the prompt only.
* The API has no authentication, and URL ingestion fetches any URL it is given.

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