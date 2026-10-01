from app.services.database import (get_due_schedules, mark_schedule_attempted, mark_schedule_completed, reset_processing_schedules,); from app.services.publisher import (PublishingError, publish_variant,)

class SchedulerWorker:
    def __init__(self, batch_size: int = 10):
        self.batch_size = batch_size

    def recover(self):
        reset_processing_schedules()

    def run_once(self) -> list[dict]:
        jobs = get_due_schedules(
            limit=self.batch_size
        )

        results = []

        for job in jobs:
            schedule_id = job["id"]
            variant_id = job["variant_id"]

            mark_schedule_attempted(
                schedule_id
            )

            try:
                result = publish_variant(
                    variant_id
                )

                mark_schedule_completed(
                    schedule_id
                )

                results.append(
                    {
                        "schedule_id": schedule_id,
                        "variant_id": variant_id,
                        "status": result["status"],
                    }
                )

            except PublishingError as error:
                results.append(
                    {
                        "schedule_id": schedule_id,
                        "variant_id": variant_id,
                        "status": "failed",
                        "error": str(error),
                    }
                )

        return results

    def run(self) -> None:
        self.recover()
        self.run_once()