from datetime import datetime, timedelta, timezone; from app.services.database import (create_post, create_variant,get_connection, get_publish_history_by_key,); from app.services.schedule import schedule_variant; from app.services.worker import SchedulerWorker; import pytest

def create_approved_discord_variant(content: str) -> int:
    post_id = create_post(
        content=content,
        source_type="markdown",
        source_url=None,
    )

    variant_id = create_variant(
        post_id=post_id,
        platform="discord",
        content=content,
    )

    connection = get_connection()

    try:
        connection.execute(
            """
            UPDATE variants
            SET status = 'approved'
            WHERE id = ?
            """,
            (variant_id,),
        )

        connection.commit()

    finally:
        connection.close()

    return variant_id

@pytest.mark.integration
def test_worker_publishes_due_variant():

    variant_id = create_approved_discord_variant(
        "Phase 5 worker test — real Discord publish."
    )

    scheduled_at = (
        datetime.now(timezone.utc)
        - timedelta(seconds=1)
    )

    schedule_id = schedule_variant(
        variant_id=variant_id,
        scheduled_at=scheduled_at,
    )

    assert schedule_id is not None

    worker = SchedulerWorker(
        batch_size=100
    )

    results = worker.run_once()

    result = next(
        item
        for item in results
        if item["variant_id"] == variant_id
    )

    assert result["status"] == "published"

@pytest.mark.integration
def test_worker_restart_does_not_duplicate_publish():

    variant_id = create_approved_discord_variant(
        "Phase 5 restart/idempotency test — this must appear only once."
    )

    scheduled_at = (
        datetime.now(timezone.utc)
        - timedelta(seconds=1)
    )

    schedule_id = schedule_variant(
        variant_id=variant_id,
        scheduled_at=scheduled_at,
    )

    assert schedule_id is not None

    worker = SchedulerWorker(
        batch_size=100
    )

    first_results = worker.run_once()

    first_result = next(
        item
        for item in first_results
        if item["variant_id"] == variant_id
    )

    assert first_result["status"] == "published"

    restarted_worker = SchedulerWorker(
        batch_size=100
    )

    restarted_worker.recover()

    from app.services.publisher import publish_variant

    second_result = publish_variant(
        variant_id
    )

    assert second_result["status"] == "already_published"

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT idempotency_key
            FROM schedules
            WHERE id = ?
            """,
            (schedule_id,),
        )

        schedule = cursor.fetchone()

        assert schedule is not None

        idempotency_key = schedule["idempotency_key"]

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM publish_history
            WHERE idempotency_key = ?
              AND result = 'success'
            """,
            (idempotency_key,),
        )

        count = cursor.fetchone()[0]

    finally:
        connection.close()

    assert count == 1