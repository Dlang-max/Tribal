"""Load runtime source from this checkout or an explicitly selected implementation worktree."""

import os
from pathlib import Path
import sys

sys.path.insert(0, os.environ.get("TRIBAL_TEST_SOURCE", str(
    Path(__file__).resolve().parents[2] / "src/tribal-mcp-server")))
