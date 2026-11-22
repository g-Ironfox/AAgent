"""Remove obsolete subprocess declarations and normalize legacy node names.

Supports local files and the current workspace API.
Fixed per-port subprocess calls still require explicit JSON rewiring."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agent"))
from workflow_contract import migrate_subprocess_workflow_format


def migrate_document(document):
    if not isinstance(document, dict):
        return document
    if isinstance(document.get("nodes"), list) and "schema_version" in document:
        return migrate_subprocess_workflow_format(document)
    # Design envelopes contain independently saved Workflow files.
    if document.get("format") == "aagent.workflow-design/1":
        return {**document, "workflows": [
            {**item, "workflow": migrate_document(item["workflow"])}
            for item in document.get("workflows", [])
        ]}
    if isinstance(document.get("workflows"), dict):
        return {**document, "workflows": {
            name: migrate_document(workflow) for name, workflow in document["workflows"].items()
        }}
    return document


def migrate_content(content):
    try:
        source = json.loads(content)
    except (ValueError, TypeError):
        return content
    migrated = migrate_document(source)
    return content if migrated == source else json.dumps(migrated, ensure_ascii=False, indent=2) + "\n"


def migrate_paths(paths, apply=False):
    count = 0
    files = set()
    for value in paths:
        path = Path(value)
        if not path.exists():
            raise FileNotFoundError(path)
        if path.is_dir():
            files.update(p for p in path.rglob("*") if p.is_file() and p.suffix in {".flow", ".json"})
        else:
            files.add(path)
    # Prepare every conversion before writing any file so conflicts fail first.
    changes = []
    for path in sorted(files):
        original = path.read_text(encoding="utf-8-sig")
        content = migrate_content(original)
        if content != original:
            changes.append((path, content))
    for path, content in changes:
        print(f"{'MIGRATE' if apply else 'WOULD MIGRATE'} {path}")
        if apply:
            path.write_text(content, encoding="utf-8")
        count += 1
    return count


def migrate_workspace(base_url, apply=False):
    import requests
    base_url = base_url.rstrip("/")
    response = requests.get(f"{base_url}/api/files", timeout=(3, 30))
    response.raise_for_status()
    changes = []
    for item in response.json()["items"]:
        url = f"{base_url}/api/files/{quote(item['file_id'], safe='')}"
        response = requests.get(url, timeout=(3, 30))
        response.raise_for_status()
        file = response.json()
        content = migrate_content(file["content"])
        if content != file["content"]:
            changes.append((url, file, content))
    for url, file, content in changes:
        print(f"{'MIGRATE' if apply else 'WOULD MIGRATE'} workspace:{file['name']}")
        if apply:
            response = requests.put(url, json={"name": file["name"], "content": content,
                                               "revision": file["revision"]}, timeout=(3, 30))
            response.raise_for_status()
    return len(changes)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="JSON/.flow files or directories")
    parser.add_argument("--workspace-url", help="WebUI service base URL")
    parser.add_argument("--apply", action="store_true", help="Write changes; default is a preview")
    args = parser.parse_args(argv)
    if not (args.paths or args.workspace_url):
        parser.error("provide paths or --workspace-url")
    count = migrate_paths(args.paths, args.apply)
    if args.workspace_url:
        count += migrate_workspace(args.workspace_url, args.apply)
    print(f"{'Migrated' if args.apply else 'Planned'} {count} documents")


if __name__ == "__main__":
    main()
