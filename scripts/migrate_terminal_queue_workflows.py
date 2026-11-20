"""Replace terminal history/wait nodes with a consuming terminal queue read.

Preview: python scripts/migrate_terminal_queue_workflows.py docs/examples
Apply:   python scripts/migrate_terminal_queue_workflows.py path/to/files --apply
Only saved workflow documents are migrated; running process snapshots are not.
History cursors and nonadjacent wait/read combinations require manual rewiring.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path


def migrate_document(document):
    result = copy.deepcopy(document)
    if not isinstance(result, dict):
        return result
    if result.get("format") == "aagent.workflow-design/1":
        for item in result.get("workflows", []):
            item["workflow"] = migrate_document(item["workflow"])
    elif isinstance(result.get("workflows"), dict):
        result["workflows"] = {name: migrate_document(value)
                               for name, value in result["workflows"].items()}
    elif isinstance(result.get("nodes"), list) and "schema_version" in result:
        nodes = {node["id"]: node for node in result["nodes"]}
        edges = result.get("connections", [])
        removed = set()
        for node in result["nodes"]:
            if node.get("type") != "wait_terminal_event":
                continue
            outgoing = [e for e in edges if e["fromId"] == node["id"]]
            if len(outgoing) != 1 or outgoing[0].get("type") != "control":
                continue
            link = outgoing[0]
            target = nodes.get(link["toId"], {})
            incoming = [e for e in edges if e["toId"] == link["toId"] and e.get("type") == "control"]
            if target.get("type") == "read_terminal_input" and incoming == [link]:
                edges.remove(link)
                for edge in edges:
                    if edge["toId"] == node["id"]:
                        edge["toId"] = target["id"]
                removed.add(node["id"])
        readers = {node["id"] for node in result["nodes"] if node.get("type") == "read_terminal_input"}
        if readers and any(node.get("type") == "wait_terminal_event" and node["id"] not in removed
                           for node in result["nodes"]):
            raise ValueError("nonadjacent terminal wait/history nodes require manual rewiring")
        if any(edge["fromId"] in readers and edge.get("type") != "control"
               and nodes.get(edge["toId"], {}).get("type") in {"list_length", "list_slice"}
               for edge in edges):
            raise ValueError("terminal history cursors/slices require manual conversion to queue reads")
        result["nodes"] = [node for node in result["nodes"] if node["id"] not in removed]
        for node in result["nodes"]:
            if node.get("type") in {"wait_terminal_event", "read_terminal_input"}:
                node["type"] = "read_terminal_queue"
    return result


def migrate_paths(paths, apply=False):
    files = set()
    for value in paths:
        path = Path(value)
        if path.is_dir():
            files.update(p for p in path.rglob("*") if p.is_file() and p.suffix in {".flow", ".json"})
        elif path.is_file():
            files.add(path)
        else:
            raise FileNotFoundError(path)
    changes = []
    for path in sorted(files):
        source = json.loads(path.read_text(encoding="utf-8-sig"))
        migrated = migrate_document(source)
        if migrated != source:
            changes.append((path, json.dumps(migrated, ensure_ascii=False, indent=2) + "\n"))
    for path, content in changes:
        print(f"{'MIGRATE' if apply else 'WOULD MIGRATE'} {path}")
        if apply:
            path.write_text(content, encoding="utf-8")
    return len(changes)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()
    migrate_paths(arguments.paths, arguments.apply)
