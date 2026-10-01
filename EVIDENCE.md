# Phase 5 Evidence

## Test Summary

The complete automated test suite passes:

```text
9 passed, 13 warnings
```

Command:

```powershell
pytest -q
```

The warnings are SQLite datetime adapter deprecation warnings and do not cause test failures.

---

## 1. Ingestion

Posts can be created using either:

* `source_type = "markdown"`
* `source_type = "url"`

The source post is stored in the database before generation.

Generation operates on the stored post content through the processing pipeline.

Relevant endpoint:

```text
POST /posts
```

---

## 2. Constraint Profiles

Platform constraints are enforced in Python code rather than relying only on the LLM prompt.

### LinkedIn

* Minimum: 150 characters
* Maximum: 3000 characters
* Maximum: 5 hashtags
* Professional/natural tone

### Instagram

* Minimum: 1 character
* Maximum: 2200 characters
* Maximum: 10 hashtags
* More conversational/engaging tone

Validation is performed by `validate_content()` in:

```text
app/services/generator.py
```

Invalid generated variants are rejected and Ollama is given another generation attempt.

Maximum generation attempts:

```text
3
```

---

## 3. Review Workflow

Variants use the following statuses:

```text
draft
approved
rejected
published
```

Only approved variants can be scheduled.

Scheduling an unapproved variant is rejected with HTTP 409.

Published variants cannot be treated as new publish operations. Repeated publish attempts use the existing idempotency record and return:

```json
{
  "status": "already_published"
}
```

Successful publishing changes the variant status to:

```text
published
```

---

## 4. Adapter Layer

Publishing uses the `SocialPublisher` interface.

Configured adapters:

```text
DiscordPublisher
MockLinkedInPublisher
MockXPublisher
```

The business logic in `publish_variant()` works against the adapter interface rather than platform-specific publishing code.

The Discord adapter is a real webhook integration.

The LinkedIn and X adapters are mock adapters used for deterministic testing.

---

## 5. Idempotent Publishing

Publishing uses an idempotency key derived from:

```text
variant ID + scheduled time
```

Example:

```text
variant-30:slot-2026-10-01T04:29:31.021046+00:00
```

Before publishing, the system checks `publish_history` for the same idempotency key.

A repeated publish returns:

```text
already_published
```

instead of publishing again.

The automated idempotency test is:

```text
tests/test_phase4.py
```

Test:

```text
test_first_publish_and_repeated_publish_are_idempotent
```

Result:

```text
PASSED
```

---

## 6. Durable Scheduling

The scheduler stores jobs in the `schedules` table.

Each schedule contains:

```text
id
variant_id
platform
scheduled_at
idempotency_key
status
attempted_at
```

Worker states include:

```text
pending
processing
completed
```

The worker:

1. Finds due schedules.
2. Marks them as processing.
3. Publishes the associated variant.
4. Records the publish result.
5. Marks the schedule completed.
6. Recovers interrupted processing jobs on restart.

Worker implementation:

```text
app/services/worker.py
```

Worker tests:

```text
tests/test_phase5_worker.py
```

The worker tests passed:

```text
2 passed
```

The restart/idempotency test verifies that a restarted worker does not create a second successful publish for the same idempotency key.

---

## 7. Publish History

Every publishing attempt is recorded in:

```text
publish_history
```

Recorded information includes:

```text
variant_id
platform
idempotency_key
result
error_message
created_at
```

History is exposed through:

```text
GET /publish-history
```

The endpoint supports a configurable result limit from 1 to 500 records.

---

## 8. Real Platform Integration

Discord was configured as the real publishing adapter using:

```text
DISCORD_WEBHOOK_URL
```

The webhook was tested successfully and produced a real Discord message.

The integration test is:

```text
tests/discord_test_phase4.py
```

The test also verifies idempotency by calling the publish operation twice and checking that only one successful history entry exists for the idempotency key.

---

## 9. Secrets

Secrets are loaded from environment variables.

The Discord webhook is stored in:

```text
.env
```

A template is provided through:

```text
.env.example
```

Secrets are not hard-coded into the application source.

---

## 10. Full Test Evidence

Command:

```powershell
pytest -q
```

Final result:

```text
9 passed, 13 warnings
```

This covers the Phase 4 publishing requirements and Phase 5 worker/scheduling requirements.
