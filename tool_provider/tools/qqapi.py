import os

import requests


def _settings() -> tuple[str, dict[str, str]]:
    base_url = os.environ["QQ_API_BASE_URL"].rstrip("/")
    headers = {
        "Authorization": f"Bearer {os.environ['QQ_API_TOKEN']}",
        "Content-Type": "application/json",
    }
    return base_url, headers


def send_group_msg(group_id: str, message: str):
    base_url, headers = _settings()
    response = requests.post(
        f"{base_url}/send_group_msg",
        headers=headers,
        json={"group_id": group_id, "message": message},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()["data"]


def send_private_msg(user_id: str, message: str):
    base_url, headers = _settings()
    response = requests.post(
        f"{base_url}/send_private_msg",
        headers=headers,
        json={"user_id": user_id, "message": message},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()["data"]