import logging
import time
from datetime import datetime, timezone

from history_repository import record_history
from queue_client import MAIN_AGENT_QUEUE_NAME, QQ_QUEUE_NAME, pop_from_queue, publish_to_queue, set_worker_status

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("aagent.qqbot.consumer")

import os
def env(name: str, fallback: str) -> str:
    return os.getenv(name) or fallback

def now():
    return datetime.now(timezone.utc).isoformat()


def handle_event(event: dict):
    """Persist QQ events and forward authorized private messages to the workflow agent."""
    record_history(event)
    print(event)
    p=event.get('payload')
    if event.get("event_type") == "qq":
        if p.get('post_type')=='message':
            if not p.get('group_id'):
                if str(p.get('user_id')) == str(env("QQ_TARGET_USER_ID","")):
                    publish_to_queue(MAIN_AGENT_QUEUE_NAME, event)
                    logger.info("QQ event persisted and forwarded queue=%s", MAIN_AGENT_QUEUE_NAME)
        else:
            pass
    


def main():
    logger.info("QQ consumer started queue=%s", QQ_QUEUE_NAME)
    while True:
        try:
            set_worker_status({"state": "idle", "updated_at": now()})
            event = pop_from_queue(QQ_QUEUE_NAME, timeout=5)
            if event is None:
                continue
            set_worker_status({"state": "processing", "event": event, "started_at": now()})
            try:
                handle_event(event)
            finally:
                set_worker_status({"state": "idle", "updated_at": now()})
        except Exception:
            logger.exception("QQ consumer failed; the event remains available to retry")
            time.sleep(2)


if __name__ == "__main__":
    main()
