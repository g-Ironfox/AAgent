# qqbot/listener.py
import asyncio
import json
import os

import websockets
from queue_client import AGENT_QUEUE_NAME, publish_to_queue

WS_URI = os.environ["QQ_WS_URI"]
WS_HEADERS = {
    "Authorization": f"Bearer {os.environ['QQ_WS_TOKEN']}"
}

TARGET_USER_ID = os.environ["QQ_TARGET_USER_ID"]


def parse_event(event: dict):
    user_id = event.get('user_id')
    group_id = event.get('group_id')
    if user_id:
        if event.get("post_type")=="notice":
            #{'time': xxx, 'self_id': xxx, 'post_type': 'notice', 'notice_type': 'notify', 'sub_type': 'input_status', 'status_text': '对方正在输入...', 'event_type': 2, 'user_id': xxx, 'group_id': 0}
            if event.get("sub_type") == "input_status":
                return {
                    "event_type":"qq",
                    "payload":{
                        "post_type":"inputing",
                        "user_id": user_id,
                    }
                }
        elif event.get("post_type")=="message":
            #{'self_id': xxx, 'user_id': xxx, 'time': xxx, 'message_id': xxx, 'message_seq': xxx, 'real_id': xxx, 'real_seq': '153', 'message_type': 'private', 'sender': {'user_id': xxx, 'nickname': 'xxx', 'card': ''}, 'raw_message': 'xxx', 'font': 14, 'sub_type': 'friend', 'message': [{'type': 'text', 'data': {'text': 'xxx'}}], 'message_format': 'array', 'post_type': 'message', 'target_id': xxx}
            return {
                "event_type":"qq",
                "payload":{
                    "post_type":"message",
                    "user_id": user_id,
                    "group_id": group_id,
                    "raw_message": event.get('raw_message'),
                    "message": event.get('message')
                }
            }
    return


async def listen():
    while True:
        try:
            async with websockets.connect(
                WS_URI,
                additional_headers=WS_HEADERS,
                open_timeout=10,
                ping_interval=20,
                ping_timeout=20
            ) as websocket:
                print("WebSocket connected")

                while True:
                    raw = await websocket.recv()
                    try:
                        event = json.loads(raw)
                    except Exception as e:
                        print("JSON decode error:", e, raw)
                        continue
                    print(event)
                    task = parse_event(event)
                    if task:
                        await asyncio.to_thread(
                            publish_to_queue,
                            AGENT_QUEUE_NAME,
                            task
                        )
                        print("已直接写入 agent 队列:", task)

        except Exception as e:
            print("WebSocket error:", e)
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(listen())