from __future__ import annotations

from typing import Any


def remap_subprocess_workflow_files(
    nodes: list[dict[str, Any]],
    references: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    replacements = {
        reference["previous_name"]: reference["name"]
        for reference in references
        if reference.get("previous_name") and reference["previous_name"] != reference["name"]
    }
    remapped = []
    for node in nodes:
        if node.get("type") != "spawn_and_wait_subprocess":
            remapped.append(node)
            continue
        arguments = node.get("arguments")
        arguments = arguments if isinstance(arguments, dict) else {}
        previous_name = arguments.get("workflow_file")
        next_name = replacements.get(previous_name)
        remapped.append(
            {
                **node,
                "arguments": {**arguments, **({"workflow_file": next_name} if next_name else {})},
            }
        )
    return remapped