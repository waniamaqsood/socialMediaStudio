from app.services.adapters.base import (PublishResult, SocialPublisher,); from app.services.adapters.discord import (DiscordPublisher,); from app.services.adapters.mock_linkedin import (MockLinkedInPublisher,); from app.services.adapters.mock_x import (MockXPublisher,); from app.services.database import (get_variant, get_schedule_by_variant, get_publish_history_by_key, create_publish_history, update_variant,);

class PublishingError(Exception):
    """
    Error raised when a variant cannot be published.
    """

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)

ADAPTERS = {
    "discord": DiscordPublisher,
    "mock_x": MockXPublisher,
    "mock_linkedin": MockLinkedInPublisher,
}

DEFAULT_ADAPTER = {
    "discord": "discord",
    "x": "mock_x",
    "linkedin": "mock_linkedin",
}


def get_publisher(platform: str) -> SocialPublisher:
    """
    Build ONLY the adapter for this platform.

    The adapter can be changed with an environment variable, for example
    PUBLISHER_LINKEDIN=mock_linkedin, without touching the publish logic.
    """
    import os

    if platform not in DEFAULT_ADAPTER:
        raise PublishingError(
            f"No publisher is configured for platform '{platform}'."
        )

    name = os.getenv(
        f"PUBLISHER_{platform.upper()}",
        DEFAULT_ADAPTER[platform],
    )

    adapter_class = ADAPTERS.get(name)

    if adapter_class is None:
        raise PublishingError(
            f"Unknown adapter '{name}' configured for platform '{platform}'."
        )

    try:
        return adapter_class()
    except RuntimeError as error:  
        raise PublishingError(str(error)) from error

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
    platform = variant["platform"]

    publisher = get_publisher(platform)
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