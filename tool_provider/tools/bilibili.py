import hashlib
import os
from pathlib import Path
from typing import Any

import requests
from pydub import AudioSegment

from tool import Tool, ToolContext


def _headers() -> dict[str, str]:
    return {
        "Cookie": os.getenv("BILIBILI_COOKIE", ""),
        "Origin": "https://www.bilibili.com",
        "Referer": "https://www.bilibili.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/91.0.4472.124 Safari/537.36",
    }


def parse_playurl(data: dict[str, Any]) -> dict[int, dict[str, Any]]:
    dash = data.get("dash")
    if dash is None and isinstance(data.get("data"), dict):
        dash = data["data"].get("dash")
    dash = dash or {}
    videos_by_quality: dict[int, list[str]] = {}
    for video in dash.get("video") or []:
        videos_by_quality.setdefault(video["id"], []).append(video["baseUrl"])
    audio_list = [
        {"id": audio["id"], "bandwidth": audio.get("bandwidth"), "url": audio["baseUrl"]}
        for audio in dash.get("audio") or []
    ]
    return {
        quality: {"video": videos, "audio": audio_list}
        for quality, videos in videos_by_quality.items()
    }


def _download(url: str, file_path: Path, context: ToolContext) -> None:
    resume_pos = file_path.stat().st_size if file_path.exists() else 0
    download_headers = _headers()
    download_headers["Range"] = f"bytes={resume_pos}-"
    response = requests.get(url, stream=True, headers=download_headers, timeout=30)
    response.raise_for_status()
    if response.status_code == 206:
        total = int(response.headers.get("Content-Length", 0)) + resume_pos
        mode = "ab"
    else:
        resume_pos = 0
        total = int(response.headers.get("Content-Length", 0))
        mode = "wb"
    downloaded = resume_pos
    with file_path.open(mode) as output:
        for chunk in response.iter_content(chunk_size=8192):
            if context.cancelled():
                return
            if chunk:
                output.write(chunk)
                downloaded += len(chunk)
                if total:
                    context.report_progress(min(downloaded / total, 1.0), "正在下载音频")


def _download_bvid(bvid: str, context: ToolContext) -> Path:
    headers = _headers()
    view = requests.get(
        "https://api.bilibili.com/x/web-interface/view",
        params={"bvid": bvid},
        headers=headers,
        timeout=30,
    ).json()
    data = view["data"]
    response = requests.get(
        "https://api.bilibili.com/x/player/wbi/playurl",
        params={"qn": 32, "fnver": 0, "fnval": 4048, "fourk": 1, "voice_balance": 1, "bvid": bvid, "cid": data["cid"]},
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    streams = parse_playurl(response.json())
    quality = max(streams)
    audio_url = streams[quality]["audio"][0]["url"]
    download_dir = Path(os.getenv("BILIBILI_DOWNLOAD_DIR", "/tmp/aagent-downloads"))
    download_dir.mkdir(parents=True, exist_ok=True)
    audio_path = download_dir / f"{hashlib.sha256(audio_url.encode()).hexdigest()}.m4s"
    mp3_path = audio_path.with_suffix(".mp3")
    _download(audio_url, audio_path, context)
    if context.cancelled():
        raise RuntimeError("download cancelled")
    AudioSegment.from_file(str(audio_path)).export(str(mp3_path), format="mp3", bitrate="192k")
    return mp3_path


def _asr(filename: Path) -> str:
    with filename.open("rb") as audio:
        response = requests.post(
            "https://frp-dry.com:63030/",
            files={"file": ("audio.wav", audio, "audio/wav")},
            data={"model": "Qwen3-asr-1.7b-fp16"},
            timeout=(10, 120),
        )
    response.raise_for_status()
    return response.json().get("text", "").replace("language Chinese<asr_text>", "").replace("language None<asr_text>", "")


class BilibiliContentTool(Tool):
    name = "bilibili.gain_content_from_bvid"
    description = "获取 B 站视频音频并转写为文本。"
    input_schema = {
        "type": "object",
        "properties": {"bvid": {"type": "string", "description": "视频 BV 号"}},
        "required": ["bvid"],
        "additionalProperties": False,
    }
    output_schema = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "视频音频的转写文本",
                "x-workflow-port-type": "content",
            }
        },
        "required": ["text"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, str]:
        return {"text": _asr(_download_bvid(arguments["bvid"], context))}


class BilibiliShortUrlTool(Tool):
    name = "bilibili.shorturl_to_bvid"
    description = "通过 B 站视频分享短链获取 BV 号。"
    input_schema = {
        "type": "object",
        "properties": {"short_url": {"type": "string", "description": "视频分享短链"}},
        "required": ["short_url"],
        "additionalProperties": False,
    }
    output_schema = {
        "type": "object",
        "properties": {
            "bvid": {
                "type": "string",
                "description": "解析得到的视频 BV 号",
                "pattern": "^BV[0-9A-Za-z]+$",
                "x-workflow-port-type": "content",
            }
        },
        "required": ["bvid"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, str]:
        response = requests.head(arguments["short_url"], allow_redirects=True, timeout=10, headers=_headers())
        response.raise_for_status()
        return {"bvid": response.url.rstrip("/").split("/")[-1]}