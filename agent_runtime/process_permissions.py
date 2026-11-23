"""Take independent runtime permission snapshots from workflow file metadata."""


def snapshot_process_permissions(permissions=None):
    permissions = permissions or {}
    levels = permissions.get("runtime", {})
    checkpoints = permissions.get("checkpoints", {})
    return {
        "runtime": {operation: levels.get(operation, 0) for operation in ("read", "write")},
        "checkpoints": {operation: checkpoints.get(operation) is True for operation in ("read", "create", "restore")},
    }
