import os, re, json, sys
import requests

def env(name: str, fallback: str) -> str:
    return os.getenv(name) or fallback

headers = {
    "Cookie": env("BILIBILI_COOKIE", ""),
    "Origin": "https://www.bilibili.com",
    "Referer": "https://www.bilibili.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

keyword = "robomaster"
page = 2


def fetch_search_page(keyword: str, page: int = 1) -> str:
    """抓取 B 站搜索页 HTML（SSR）"""
    params = {"keyword": keyword, "page": page,"o":30}
    res = requests.get("https://search.bilibili.com/all", params=params, headers=headers, timeout=30)
    res.raise_for_status()
    return res.text


# ---------- 方式一：解析 window.__pinia 内嵌 JSON ----------

def _parse_js_value(s: str, i: int):
    """解析一个 JS 字面量（数字/字符串/null/true/false/void 0），返回 (值, 下一索引)"""
    n = len(s)
    while i < n and s[i] in " \t\r\n":
        i += 1
    if i >= n:
        raise ValueError("JS 值解析到末尾")
    c = s[i]
    if c in "\"'":                        # 字符串
        quote = c
        i += 1
        buf = []
        while i < n:
            ch = s[i]
            if ch == "\\":
                nxt = s[i + 1] if i + 1 < n else ""
                if nxt == "u":
                    buf.append(chr(int(s[i + 2:i + 6], 16)))
                    i += 6
                elif nxt == "n":
                    buf.append("\n"); i += 2
                elif nxt == "t":
                    buf.append("\t"); i += 2
                elif nxt == "r":
                    buf.append("\r"); i += 2
                elif nxt in "\\/\"'":
                    buf.append(nxt); i += 2
                else:
                    buf.append(nxt); i += 2
            elif ch == quote:
                i += 1
                break
            else:
                buf.append(ch); i += 1
        return "".join(buf), i
    if s.startswith("void", i):           # void 0 / void 1 ...
        j = i + 4
        while j < n and (s[j].isdigit() or s[j] in " \t\r\n"):
            j += 1
        return None, j
    if s.startswith("null", i):
        return None, i + 4
    if s.startswith("true", i):
        return True, i + 4
    if s.startswith("false", i):
        return False, i + 5
    m = re.match(r"-?\d+(\.\d+)?", s[i:])   # 数字
    if m:
        t = m.group(0)
        return (float(t) if "." in t else int(t)), i + len(t)
    m = re.match(r"[A-Za-z_$][A-Za-z0-9_$]*", s[i:])  # 裸标识符（按未定义处理）
    if m:
        return ("IDENT", m.group(0)), i + len(m.group(0))
    raise ValueError(f"无法解析的 JS 值: {s[i:i+20]!r}")


def _parse_js_array(text: str) -> list:
    """解析 (0,"",null,...,"x") 这样的 IIFE 参数列表"""
    i = 0
    n = len(text)
    if i < n and text[i] == "(":
        i += 1
    values = []
    while i < n:
        while i < n and text[i] in " \t\r\n":
            i += 1
        if i >= n or text[i] == ")":
            break
        val, i = _parse_js_value(text, i)
        values.append(None if (isinstance(val, tuple) and val[0] == "IDENT") else val)
        while i < n and text[i] in " \t\r\n":
            i += 1
        if i < n and text[i] == ",":
            i += 1
    return values


def _resolve_object(obj_text: str, var_map: dict) -> str:
    """把对象文本里的裸标识符替换成 var_map 中的值，产出合法 JSON 文本"""
    out = []
    i = 0
    n = len(obj_text)
    while i < n:
        c = obj_text[i]
        if c == '"':                       # 原样复制字符串（含 \u002F 等转义）
            j = i + 1
            out.append(c)
            while j < n:
                out.append(obj_text[j])
                if obj_text[j] == "\\":
                    out.append(obj_text[j + 1])
                    j += 2
                    continue
                if obj_text[j] == '"':
                    j += 1
                    break
                j += 1
            i = j
            continue
        if c.isalpha() or c == "_" or c == "$":   # 裸标识符 → 查表替换
            m = re.match(r"[A-Za-z_$][A-Za-z0-9_$]*", obj_text[i:])
            name = m.group(0)
            if name in var_map:
                v = var_map[name]
                if isinstance(v, str):
                    out.append(json.dumps(v, ensure_ascii=False))
                elif v is None:
                    out.append("null")
                elif v is True:
                    out.append("true")
                elif v is False:
                    out.append("false")
                else:
                    out.append(str(v))
            else:
                raise ValueError(f"对象里出现未定义标识符: {name}")
            i += len(name)
            continue
        out.append(c)
        i += 1
    return "".join(out)


def parse_pinia_data(html: str) -> dict:
    """从 HTML 中提取 window.__pinia 并解析为 dict"""
    start = html.find("window.__pinia=")
    if start == -1:
        raise ValueError("HTML 里没有 window.__pinia")
    body = html[start + len("window.__pinia="):]
    script_end = body.find("</script>")
    if script_end != -1:
        body = body[:script_end]

    # 参数名: (function(a,b,...){return
    m = re.search(r"\(function\s*\(([^)]*)\)\s*\{\s*return\s*", body)
    if not m:
        raise ValueError("找不到 IIFE 结构")
    params = [p.strip() for p in m.group(1).split(",") if p.strip()]

    # 对象本体: return { ... }
    obj_start = m.end()
    depth, i = 0, obj_start
    while i < len(body):
        if body[i] == "{":
            depth += 1
        elif body[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    obj_text = body[obj_start:i + 1]
    rest = body[i + 1:]                    # 形如 })(0,"",null,...)
    am = re.search(r"\)\s*\((.*)\)\s*$", rest, re.S)
    if not am:
        raise ValueError("找不到 IIFE 参数")
    args_values = _parse_js_array(am.group(1))

    var_map = dict(zip(params, args_values))
    resolved = _resolve_object(obj_text, var_map)
    return json.loads(resolved)


def strip_tags(text):
    return re.sub(r"<[^>]+>", "", text) if text else ""


def extract_videos(data: dict) -> list:
    """从解析结果中提取视频列表（过滤广告卡片）"""
    all_res = data["searchResponse"]["searchAllResponse"]
    videos = []
    for item in all_res.get("result", []):
        if item.get("type") != "video":
            continue
        videos.append({
            "bvid": item.get("bvid"),
            "aid": item.get("aid"),
            "arcurl": item.get("arcurl"),
            "title": strip_tags(item.get("title")),
            "author": item.get("author"),
            "mid": item.get("mid"),
            "play": item.get("play"),
            "danmaku": item.get("danmaku"),
            "review": item.get("video_review"),
            "favorites": item.get("favorites"),
            "like": item.get("like"),
            "duration": item.get("duration"),
            "pubdate": item.get("pubdate"),
            "pubstr": item.get("pubstr"),
            "tags": item.get("tag"),
            "pic": item.get("pic"),
            "typeid": item.get("typeid"),
            "typename": item.get("typename"),
        })
    return videos


# ---------- 方式二（备用）：从渲染好的 HTML 卡片里正则提取 ----------

def extract_videos_from_dom(html: str) -> list:
    videos = []
    card_re = re.compile(
        r'<div class="bili-video-card"[\s\S]*?'
        r'<a href="[^"]*/video/(BV[\w]+)/?"'
        r'[\s\S]*?bili-video-card__stats__duration"[^>]*>([^<]+)'
        r'[\s\S]*?bili-video-card__info--tit" title="([^"]+)"'
        r'[\s\S]*?bili-video-card__info--author"[^>]*>([^<]+)'
        r'[\s\S]*?bili-video-card__info--date"[^>]*>\s*·?\s*([^<]+)'
    )
    for m in card_re.finditer(html):
        bvid, duration, title, author, date = m.groups()
        videos.append({
            "bvid": bvid,
            "title": strip_tags(title),
            "author": author.strip(),
            "duration": duration,
            "pubstr": date.strip(),
        })
    return videos


def main():
    html = fetch_search_page(keyword, page)
    with open("1.txt", "w", encoding="utf-8") as f:
        f.write(html)

    try:
        data = parse_pinia_data(html)
        videos = extract_videos(data)
        total = data["searchResponse"]["searchAllResponse"]["pageinfo"]["video"]["total"]
        src = "pinia JSON"
    except Exception as e:
        print(f"[warn] pinia 解析失败({e})，改用 HTML 卡片提取")
        videos = extract_videos_from_dom(html)
        total = len(videos)
        src = "HTML 卡片"

    print(f"关键词: {keyword} | 视频总数: {total} | 本页提取: {len(videos)} 条 | 来源: {src}")
    for i, v in enumerate(videos, 1):
        print(f"{i:>2}. [{v.get('play', '?'):>8}] {v['bvid']} {v['title'][:40]} - {v['author']} ({v.get('pubstr', '')})")

if __name__ == "__main__":
    main()