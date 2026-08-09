import requests,os,json
def env(name: str, fallback: str) -> str:
    return os.getenv(name) or fallback


def parse_playurl(data):
    """把 playurl(DASH) 接口返回转换成 {清晰度: {"video": [url...], "audio": [{id, bandwidth, url}...]}}。
    data 可以传整个接口返回(含 code/message/data),也可以只传 data 那一层。
    视频按清晰度分组,每个清晰度保留全部编码版本(AVC/HEVC/AV1);
    音频全部保留,并带上 id(码率标识)和 bandwidth,方便区分 64K/132K/192K。
    """
    # dash 可能藏在 data["data"]["dash"] 里,两种传法都兼容
    dash = data.get("dash")
    if dash is None and isinstance(data.get("data"), dict):
        dash = data["data"].get("dash")
    dash = dash or {}

    videos = dash.get("video") or []
    audios = dash.get("audio") or []

    # 把视频流按清晰度分组,结构: {清晰度id: [视频url1, 视频url2, ...]}
    # 清晰度id对照: 116=1080P60, 80=1080P, 64=720P, 32=480P, 16=360P
    # 同一个清晰度下可能有多个编码版本(AVC/HEVC/AV1),所以值是 url 列表
    videos_by_quality = {}
    for v in videos:
        qid = v["id"]        # 这条视频流的清晰度,比如 80
        url = v["baseUrl"]   # 这条视频流的下载地址
        if qid not in videos_by_quality:
            videos_by_quality[qid] = []       # 第一次出现这个清晰度,先建个空列表
        videos_by_quality[qid].append(url)    # 把这条视频流地址加进去

    # 音频全部保留,带上 id 和码率,方便区分哪个是哪个
    audio_list = [
        {
            "id": a["id"],
            "bandwidth": a.get("bandwidth"),
            "url": a["baseUrl"],
        }
        for a in audios
    ]

    result = {}
    for qid, urls in videos_by_quality.items():
        result[qid] = {
            "video": urls,
            "audio": audio_list,
        }
    return result


def download_with_resume(url, file_path, chunk_size=8192):
    resume_pos = os.path.getsize(file_path) if os.path.exists(file_path) else 0

    headers = {"Range": f"bytes={resume_pos}-"}
    resp = requests.get(url, stream=True, headers=headers, timeout=30)
    resp.raise_for_status()

    if resp.status_code == 206:          # 服务端支持断点续传
        total = int(resp.headers.get("Content-Length", 0)) + resume_pos
        mode = "ab"
    else:                                 # 不支持，从头下
        resume_pos = 0
        total = int(resp.headers.get("Content-Length", 0))
        mode = "wb"

    with open(file_path, mode) as f:
        downloaded = resume_pos
        for chunk in resp.iter_content(chunk_size=chunk_size):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    print(f"\r{downloaded}/{total}  {downloaded/total*100:.1f}%", end="")
    print("\n下载完成")

header={
    "Cookie": env("BILIBILI_COOKIE", ""),
    "Origin": "https://www.bilibili.com",
    "Referer": "https://www.bilibili.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

view = requests.get(
    "https://api.bilibili.com/x/web-interface/view",
    params={"bvid": "BV181Kp6aEnX"},
    headers=header,
).json()

data = view["data"]
title=data['title']
print(data["cid"],data['title'])                  # 第一P的 cid
for p in data["pages"]:             # 多P视频的每一P
    print(p["cid"], p["part"], p["duration"])

bvid = "BV181Kp6aEnX"
cid = data["cid"]
url = f"https://api.bilibili.com/x/player/wbi/playurl?qn=32&fnver=0&fnval=4048&fourk=1&voice_balance=1&bvid={bvid}&cid={cid}"
resp = requests.get(url, headers=header)
resp.raise_for_status()
url = parse_playurl(resp.json())
video=url[max(url.keys())]['video'][0]
audio=url[max(url.keys())]['audio'][0]['url']
print(video,audio)

resp = requests.get(audio, stream=True, headers=header)
resp.raise_for_status()

total = int(resp.headers.get("Content-Length", 0))
downloaded = 0

with open(f"{title}.m4s", "wb") as f:
    for chunk in resp.iter_content(chunk_size=8192):
        f.write(chunk)
        downloaded += len(chunk)
        if total:
            print(f"\r{downloaded/total*100:.1f}%", end="")