# agent/qqapi.py
import os

import requests

baseurl = os.environ["QQ_API_BASE_URL"].rstrip("/")
headers = {
    "Authorization": f"Bearer {os.environ['QQ_API_TOKEN']}",
    "Content-Type": "application/json"
}

def send_group_msg(group_id, message):
    res = requests.post(
        baseurl + "/send_group_msg",
        headers=headers,
        json={"group_id": group_id, "message": message},
        timeout=15
    )
    res.raise_for_status()
    return res.json()['data']

def send_private_msg(user_id, message):
    res = requests.post(
        baseurl + "/send_private_msg",
        headers=headers,
        json={"user_id": user_id, "message": message},
        timeout=15
    )
    res.raise_for_status()
    return res.json()['data']

def send_private_img(user_id, img_bs64):
    data_url = f"base64://{img_bs64}"
    res = requests.post(
        baseurl + "/send_private_msg",
        headers=headers,
        json={
            "user_id": user_id,
            "message": {
                "type": "image",
                "data": {
                    "file": data_url
                }
            }
        },
        timeout=15
    )
    res.raise_for_status()
    return res.json()['data']

def get_group_list():
    res = requests.post(
        baseurl + "/get_group_list",
        headers=headers,
        timeout=15
    )
    res.raise_for_status()
    return res.json()['data']

def get_group_member_info(group_id, user_id):
    res = requests.post(
        baseurl + "/get_group_member_info",
        headers=headers,
        json={'group_id': group_id, 'user_id': user_id},
        timeout=15
    )
    res.raise_for_status()
    return res.json()['data']

def get_group_msg_history(group_id, message_seq, count):
    res = requests.post(
        baseurl + "/get_group_msg_history",
        headers=headers,
        json={
            "group_id": group_id,
            "message_seq": message_seq,
            "count": count
        },
        timeout=15
    )
    res.raise_for_status()
    return res.json()['data']