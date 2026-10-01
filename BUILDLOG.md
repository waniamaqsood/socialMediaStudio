# BUILDLOG

## Project

Social Media Studio — FlyRank Internship Backend Track Capstone

## AI Usage

AI tools were used during development as a coding and debugging assistant.

### Where AI helped

- Helped reason about the overall backend architecture and separation of responsibilities.
- Helped design the SQLite data model for posts, variants, schedules, and publish history.
- Helped implement and review FastAPI endpoints.
- Helped develop the Ollama-based generation service.
- Helped reason about platform constraint validation.
- Helped implement the SocialPublisher adapter architecture.
- Helped debug publishing and idempotency behaviour.
- Helped design scheduler and worker restart handling.
- Helped write and refine automated tests.
- Helped review README and evidence documentation against the capstone requirements.

### Where AI was wrong or incomplete

AI-generated suggestions were not always correct and were verified against the actual application behaviour.

Examples:

- An early publisher implementation checked the `published` status before checking the existing idempotency record. This caused a repeated publish to be rejected instead of returning an idempotent result.
- An early publishing flow checked for a schedule before checking whether the variant was approved. This produced the wrong error for unapproved variants.
- Database locking and missing database helper issues were encountered during testing and required direct debugging and code changes.
- The original generation approach used Gemini during an earlier implementation attempt. The project was subsequently moved to local Ollama because the Gemini model/API configuration was unavailable or unreliable in the development environment.
- Test execution and real Discord integration were used to verify that proposed fixes actually worked.

### Verification

The final implementation was tested locally using pytest.

Current full test result:

    9 passed, 13 warnings

The warnings are SQLite/Python datetime adapter deprecation warnings and did not cause test failures.

A real Discord webhook integration was also tested successfully.

## Development Approach

The implementation was built incrementally through the capstone phases:

1. System design
2. Ingestion and generation
3. Review workflow
4. Publishing adapters and idempotency
5. Scheduling, publish history, restart handling, testing, and documentation

AI assistance was treated as a development aid rather than as a substitute for testing or understanding the implementation. Code suggestions were checked against the running application and automated tests before being considered complete.
