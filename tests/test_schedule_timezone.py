from datetime import datetime, timedelta, timezone

from app.services.database import (
    create_post,
    create_variant,
    get_due_schedules,
    update_variant,
)
from app.services.schedule import schedule_variant


def approved_variant() -> int:
    post_id = create_post(content="post", source_type="markdown")
    variant_id = create_variant(post_id=post_id, platform="x", content="hello")
    update_variant(variant_id, status="approved")
    return variant_id


def test_future_schedule_is_not_due():
    schedule_variant(approved_variant(), datetime.now(timezone.utc) + timedelta(hours=3))
    assert get_due_schedules() == []


def test_past_schedule_is_due():
    variant_id = approved_variant()
    schedule_variant(variant_id, datetime.now(timezone.utc) - timedelta(minutes=1))
    assert [s["variant_id"] for s in get_due_schedules()] == [variant_id]


def test_non_utc_input_is_handled():
    plus5 = timezone(timedelta(hours=5))
    schedule_variant(approved_variant(), datetime.now(plus5) + timedelta(hours=3))
    assert get_due_schedules() == []