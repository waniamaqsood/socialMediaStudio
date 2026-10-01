from app.services.adapters.base import (PublishResult, SocialPublisher,); from app.services.adapters.discord import (DiscordPublisher,); from app.services.adapters.mock_linkedin import (MockLinkedInPublisher,); from app.services.adapters.mock_x import (MockXPublisher,); from app.services.database import (get_variant, get_schedule_by_variant, get_publish_history_by_key, create_publish_history, update_variant,);

class PublishingError(Exception):
    """
    Error raised when a variant cannot be published.
    """

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def get_publishers() -> dict[str, SocialPublisher]:
    """
    Return platform adapters selected through environment configuration.

    Each platform can be mapped to a different adapter without
    changing the publishing business logic.
    """
    import os

    adapter_map = {
        "discord": DiscordPublisher,
        "mock_x": MockXPublisher,
        "mock_linkedin": MockLinkedInPublisher,
    }

    publishers = {}

    for platform in ("discord", "x", "linkedin"):
        configured_adapter = os.getenv(
            f"PUBLISHER_{platform.upper()}",
            platform if platform == "discord" else f"mock_{platform}",
        )

        adapter_class = adapter_map.get(configured_adapter)

        if adapter_class is None:
            raise PublishingError(
                f"Unknown adapter '{configured_adapter}' "
                f"configured for platform '{platform}'."
            )

        publishers[platform] = adapter_class()

    return publishers

def publish_variant(
    variant_id: int,
) -> dict:
    """
    Publish an approved, scheduled variant.

    Publishing is idempotent using the schedule's
    idempotency key.
    """

    variant = get_variant(variant_id)

    if variant is None:
        raise PublishingError(
            f"Variant {variant_id} does not exist."
        )

    # Published variants are handled through the idempotency
    # path so retries return already_published.
    if variant["status"] == "published":
        schedule = get_schedule_by_variant(variant_id)

        if schedule is not None:
            idempotency_key = schedule["idempotency_key"]

            previous_publish = get_publish_history_by_key(
                idempotency_key
            )

            if previous_publish is not None:
                return {
                    "variant_id": variant_id,
                    "platform": variant["platform"],
                    "status": "already_published",
                    "idempotency_key": idempotency_key,
                }

        raise PublishingError(
            f"Variant {variant_id} has already been published."
        )

    # Only approved variants may enter the publishing flow.
    if variant["status"] != "approved":
        raise PublishingError(
            f"Variant {variant_id} cannot be published. "
            f"Current status is '{variant['status']}'. "
            "Only approved variants can be published."
        )

    schedule = get_schedule_by_variant(
        variant_id
    )

    if schedule is None:
        raise PublishingError(
            f"Variant {variant_id} has no schedule."
        )

    idempotency_key = schedule["idempotency_key"]

    previous_publish = get_publish_history_by_key(
        idempotency_key
    )

    if previous_publish is not None:
        return {
            "variant_id": variant_id,
            "platform": variant["platform"],
            "status": "already_published",
            "idempotency_key": idempotency_key,
        }

    publishers = get_publishers()

    platform = variant["platform"]

    publisher = publishers.get(platform)

    if publisher is None:
        raise PublishingError(
            f"No publisher is configured for "
            f"platform '{platform}'."
        )

    result: PublishResult = publisher.publish(
        variant["content"]
    )

    if not result.success:
        create_publish_history(
            variant_id=variant_id,
            platform=platform,
            idempotency_key=idempotency_key,
            result="failed",
            error_message=result.error_message,
        )

        raise PublishingError(
            f"Publishing to {platform} failed: "
            f"{result.error_message}"
        )

    create_publish_history(
        variant_id=variant_id,
        platform=platform,
        idempotency_key=idempotency_key,
        result="success",
        error_message=None,
    )

    update_variant(
        variant_id=variant_id,
        status="published",
    )

    return {
        "variant_id": variant_id,
        "platform": platform,
        "status": "published",
        "idempotency_key": idempotency_key,
    }