import time

from app.services.database import init_db
from app.services.worker import SchedulerWorker

POLL_SECONDS = 5

if __name__ == "__main__":
    init_db()
    worker = SchedulerWorker()
    worker.recover()
    print(f"Worker started. Checking every {POLL_SECONDS}s. Ctrl+C to stop.")
    try:
        while True:
            for result in worker.run_once():
                print(result)
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("Worker stopped.")