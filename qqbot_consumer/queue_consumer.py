import logging
import time,json
from datetime import datetime, timezone
from llm import chat_with_deepseek

from history_repository import get_documents, record_history
from queue_client import MAIN_AGENT_QUEUE_NAME, QQ_AGENT_QUEUE_NAME, get_agent_settings, pop_from_queue, publish_to_queue, set_worker_status

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("aagent.qqbot.consumer")

import os
def env(name: str, fallback: str) -> str:
    return os.getenv(name) or fallback

def now():
    return datetime.now(timezone.utc).isoformat()


def system_prompt_from_documents():
    settings = get_agent_settings()
    selected_documents = get_documents(settings.get("document_ids", []))
    return "\n\n".join(
        document.get('content', '')
        for document in selected_documents
    )





def send_group_message(group_id,message):
    e = {
        "event_type":"rpc_apply",
        "payload":{
            "subagent_name":"qqbot",
            "callback_queue_name":QQ_AGENT_QUEUE_NAME,
            "tool_name":"qq_send_group_msg",
            "tool_arguments":{"group_id":group_id,"messge":message}
        }
    }
    print(e)
    publish_to_queue(MAIN_AGENT_QUEUE_NAME,e)
    return "请求中"



def handle_event(event: dict):
    """Demo hook: persist the QQ event, then forward it to the main agent."""
    record_history(event)
    print(event)
    p=event.get('payload')
    if event.get("event_type") == "qq":
        if p.get('post_type')=='message':
            if not p.get('group_id'):
                if str(p.get('user_id')) == str(env("QQ_TARGET_USER_ID","")):
                    publish_to_queue(MAIN_AGENT_QUEUE_NAME, event)
                    logger.info("QQ event persisted and forwarded queue=%s", MAIN_AGENT_QUEUE_NAME)
            elif f'[CQ:at,qq={env("QQ_BOT_ID","")}]' in p.get('raw_message'):
                messages = [
                    {"role":"system","content":system_prompt_from_documents()},
                    {"role":"user","content":""}
                ]
                content , reasoning , tool_calls = chat_with_deepseek(messages)
                send_group_message(p.get('group_id'),content)
        else:
            pass
    


def main():
    logger.info("QQ consumer started queue=%s", QQ_AGENT_QUEUE_NAME)
    while True:
        try:
            set_worker_status({"state": "idle", "updated_at": now()})
            event = pop_from_queue(QQ_AGENT_QUEUE_NAME, timeout=5)
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
