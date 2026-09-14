"""Fetch and print a parsed workflow for debugging."""

from __future__ import annotations

import argparse
import json
import sys

from workflow_parser import _read_workflow, parse_workflow
from workflow_validator import validate_workflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch a workflow from MongoDB and print its parsed runtime map."
    )
    parser.add_argument(
        "name",
        nargs="?",
        help="workflow name; if omitted, prompt for it",
    )
    parser.add_argument(
        "--by-id",
        action="store_true",
        help="treat name as a MongoDB ObjectId instead of a workflow name",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="skip workflow validation before parsing",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    workflow_name = args.name or input("Workflow name: ").strip()
    if not workflow_name:
        print("workflow name cannot be empty", file=sys.stderr)
        return 2

    try:
        workflow_document = _read_workflow(workflow_name, by_id=args.by_id)
        if not args.no_validate:
            validate_workflow(workflow_document)
        parsed_workflow = parse_workflow(workflow_document)
    except Exception as error:
        print(f"failed to parse workflow {workflow_name!r}: {error}", file=sys.stderr)
        return 1

    print(json.dumps(parsed_workflow, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
