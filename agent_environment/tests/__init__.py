"""Tests for the agent_environment service."""

import sys
from pathlib import Path

# Production modules use service-local top-level imports because the container
# starts the application with /app as its module root.
_SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVICE_ROOT))
