"""Read an ordered, branch-local file recovery plan without changing the workspace."""
from urllib.parse import quote


def build_file_recovery_plan(file_id, stable_file_id, checkpoint_seq, request):
    """Try each distinct earlier content once and stop at the stable anchor.

    All reads use the existing workspace API, including its file/checkpoint
    permission checks. Only the selected checkpoint's ancestors are considered.
    """
    if isinstance(checkpoint_seq, bool) or not isinstance(checkpoint_seq, int) or checkpoint_seq < 0:
        raise ValueError("checkpoint_seq must be a non-negative integer")
    current = request("GET", "/" + quote(file_id, safe=""))["content"]
    stable = request("GET", "/" + quote(stable_file_id, safe=""))["content"]
    if current == stable:
        return {"versions": []}
    versions = []
    seen_contents = {current}
    seen_checkpoints = set()
    cursor = checkpoint_seq
    while cursor:
        if cursor in seen_checkpoints:
            raise ValueError("checkpoint ancestry contains a cycle")
        seen_checkpoints.add(cursor)
        diff = request("GET", f"/checkpoints/{cursor}/diff")
        parent = diff["parent_seq"] or 0
        for change in diff["changes"]:
            previous = change.get("before_content")
            if change["file_id"] != file_id or previous is None or previous in seen_contents:
                continue
            seen_contents.add(previous)
            versions.append({"content": previous, "checkpoint_seq": parent,
                             "source": "stable" if previous == stable else "checkpoint"})
            if previous == stable:
                return {"versions": versions}
        cursor = parent
    # The immutable installation anchor is also usable when no older checkpoint
    # contains it (for example, an imported main with only one saved version).
    versions.append({"content": stable, "checkpoint_seq": 0, "source": "stable"})
    return {"versions": versions}
