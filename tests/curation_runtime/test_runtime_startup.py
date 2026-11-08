"""Exercise command startup without configured storage or any remote model request."""

import os
from pathlib import Path
import subprocess
import sys

import server


# Fail module command startup clearly before attempting any backend connection.
def test_module_cli_requires_explicit_project_configuration(tmp_path):
    source = str(Path(server.__file__).parent)
    environment = {name: os.environ[name] for name in ("PATH", "HOME") if name in os.environ}
    environment["PYTHONPATH"] = source
    result = subprocess.run([sys.executable, "-m", "server"], env=environment,
                            cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "TRIBAL_PROJECT_ID" in result.stderr
    assert "ModuleNotFoundError" not in result.stderr
    assert "Connection refused" not in result.stderr
