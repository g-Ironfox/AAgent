"""Cross-file permission contract for the experimental evolving bundle."""
from __future__ import annotations


def configure_iterator_access(items):
    by_role = {item["role"]: item for item in items}
    iterator = by_role["iterator"]["permissions"]
    # Data writes require >= target.required.write, NOT >. Never solve this
    # by lowering the main's protection or granting the iterator level 4.
    targets = [by_role[role]["permissions"] for role in ("main", "experience")]
    iterator["runtime"]["write"] = max(p["required"]["write"] for p in targets)
    iterator["runtime"]["read"] = max(2, by_role["workflow_reference"]["permissions"]["required"]["read"],
                                        *(p["required"]["read"] for p in targets))
    iterator["checkpoints"]["create"] = True
    validate_bundle_access(items)


def validate_bundle_access(items):
    by_role = {item["role"]: item["permissions"] for item in items}
    iterator = by_role["iterator"]
    for role in ("main", "experience", "workflow_reference"):
        if iterator["runtime"]["read"] < by_role[role]["required"]["read"]:
            raise ValueError(f"iterator cannot read {role}")
    for role in ("main", "experience"):
        if iterator["runtime"]["write"] < by_role[role]["required"]["write"]:
            raise ValueError(f"iterator cannot write {role}: runtime.write < required.write")
    for role in ("stable", "bootstrap", "iterator", "workflow_reference"):
        if iterator["runtime"]["write"] >= by_role[role]["required"]["write"]:
            raise ValueError(f"iterator must not be able to write protected {role}")
    if by_role["bootstrap"]["runtime"]["read"] < iterator["required"]["read"]:
        raise ValueError("bootstrap cannot read iterator")
    if not iterator["checkpoints"]["create"] or iterator["checkpoints"]["restore"]:
        raise ValueError("iterator must create checkpoints but cannot restore them")
