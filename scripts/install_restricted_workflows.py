"""Install a fresh fixed workflow bundle through the existing workspace API.

Example: python scripts/install_restricted_workflows.py --model MODEL_ID --install
Without --install this command only previews names and permissions.
"""
import argparse
from functools import partial
import json
import re
import urllib.error
import urllib.request

from build_restricted_workflows import build_bundle


def request(base_url, method, path, payload=None):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(base_url.rstrip("/") + "/api/files" + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"workspace API returned HTTP {error.code} for {method} {path}") from error
    except urllib.error.URLError as error:
        raise RuntimeError("cannot connect to workspace API; start WebUI or provide --url") from error


def install_bundle(api, model, prefix="restricted-agent", max_turns=8):
    return install_files(api, model, prefix, partial(build_bundle, max_turns=max_turns))


def install_files(api, model, prefix, builder):
    """Bind a fresh bundle in dependency order without overwriting existing files."""
    if not isinstance(model, str) or not model.strip() or model.startswith("REPLACE_WITH_"):
        raise ValueError("an enabled model ID is required")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", prefix):
        raise ValueError("prefix must contain 1-80 ASCII letters, digits, hyphens or underscores")
    bundle = builder(model=model, prefix=prefix)
    existing = {item["name"] for item in api("GET", "")["items"]}
    conflicts = sorted(existing & {item["name"] for item in bundle})
    if conflicts:
        raise ValueError("existing files will not be overwritten; choose another --prefix: " + ", ".join(conflicts))
    installed = {}
    for index in range(len(bundle)):
        # Earlier creates supply exact file IDs to all later definitions.
        bound = builder(model=model, prefix=prefix,
                             experience_id=installed.get("experience", {}).get("file_id", "UNBOUND_EXPERIENCE"),
                             main_id=installed.get("main", {}).get("file_id", "UNBOUND_MAIN"),
                             stable_id=installed.get("stable", {}).get("file_id", "UNBOUND_STABLE"))
        item = bound[index]
        content = item["content"]
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False, indent=2) + "\n"
        file = api("POST", "", {"name": item["name"], "content": content, "permissions": item["permissions"]})
        installed[item["role"]] = {"file_id": file["file_id"], "name": file["name"]}
    # Preserve the fully installed initial state, including the immutable anchor.
    checkpoint = api("POST", "/checkpoints", {"name": prefix + ": installed baseline"})
    return {"files": installed, "baseline_checkpoint": checkpoint["seq"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="enabled model ID used for task and experience LLM nodes")
    parser.add_argument("--url", default="http://127.0.0.1:8081")
    parser.add_argument("--prefix", default="restricted-agent")
    parser.add_argument("--max-turns", type=int, default=8)
    parser.add_argument("--install", action="store_true", help="create five workspace files and an initial checkpoint")
    args = parser.parse_args()
    if not args.install:
        preview = [{key: value for key, value in item.items() if key != "content"}
                   for item in build_bundle(model=args.model, prefix=args.prefix, max_turns=args.max_turns)]
        print(json.dumps({"preview": preview, "install": False}, ensure_ascii=False, indent=2))
        return
    try:
        result = install_bundle(lambda method, path, payload=None: request(args.url, method, path, payload),
                                args.model, args.prefix, args.max_turns)
    except (RuntimeError, ValueError) as error:
        parser.exit(1, f"Installation stopped: {error}\nAny files already created were retained. Retry with a new prefix after resolving the problem.\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("Create a process from " + result["files"]["bootstrap"]["name"] + " with a task input.")


if __name__ == "__main__":
    main()
