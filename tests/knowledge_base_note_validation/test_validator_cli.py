"""Exercise the public validator command as a real subprocess."""
from pathlib import Path
import subprocess
import sys


ENTRYPOINT = (
    Path(__file__).resolve().parents[2]
    / "agent-knowledge-base/validation/v1/validate_knowledge_base_notes.py"
)


# Verify cli exposes usage for the documented entrypoint.
def test_cli_exposes_usage_for_the_documented_entrypoint():
    """A missing or unusable command must fail the first public smoke check."""
    result = subprocess.run(
        [sys.executable, str(ENTRYPOINT), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--project-id" in result.stdout
    assert "--json" in result.stdout


# Execute the real command with the active Python interpreter and capture its output.
def run_validator(*arguments):
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT), *(str(argument) for argument in arguments)],
        capture_output=True,
        text=True,
        check=False,
    )


# Verify valid vault json is an empty array.
def test_valid_vault_json_is_an_empty_array(valid_vault):
    import json
    result = run_validator(valid_vault, "--json", "--project-id", "checkout-demo")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []
    assert "Traceback" not in result.stderr


# Verify invalid vault json is a useful issue array.
def test_invalid_vault_json_is_a_useful_issue_array(valid_vault):
    import json
    from conftest import note_path, set_raw_field
    set_raw_field(note_path(valid_vault), "status", "invalid")
    result = run_validator(valid_vault, "--json")
    assert result.returncode == 1, result.stderr
    issues = json.loads(result.stdout)
    assert isinstance(issues, list) and issues
    assert any(issue["path"].endswith("Expired Code Accepted.md") for issue in issues)
    for issue in issues:
        assert set(issue) == {"path", "code", "message"}
        assert all(isinstance(value, str) and value.strip() for value in issue.values())
    assert "Traceback" not in result.stderr


# Verify project id cli argument enforces project scope.
def test_project_id_cli_argument_enforces_project_scope(valid_vault):
    result = run_validator(valid_vault, "--project-id", "unauthorized-project", "--json")
    assert result.returncode == 1
    import json
    assert json.loads(result.stdout)


# Verify text output reports success for valid vault.
def test_text_output_reports_success_for_valid_vault(valid_vault):
    result = run_validator(valid_vault)
    assert result.returncode == 0
    assert result.stdout.strip()
    assert "Traceback" not in result.stderr


# Verify text output identifies invalid note.
def test_text_output_identifies_invalid_note(valid_vault):
    from conftest import note_path, set_raw_field
    set_raw_field(note_path(valid_vault), "status", "invalid")
    result = run_validator(valid_vault)
    assert result.returncode == 1
    assert "Expired Code Accepted.md" in result.stdout + result.stderr
    assert "Traceback" not in result.stdout + result.stderr


# Verify missing root reports validation failure without traceback.
def test_missing_root_reports_validation_failure_without_traceback(tmp_path):
    result = run_validator(tmp_path / "Missing vault", "--json")
    assert result.returncode == 1
    import json
    assert json.loads(result.stdout)
    assert "Traceback" not in result.stderr


# Verify missing required cli argument is a usage error.
def test_missing_required_cli_argument_is_a_usage_error():
    result = run_validator()
    assert result.returncode == 2
    assert "usage" in result.stderr.lower()


# Verify unknown cli flag is a usage error.
def test_unknown_cli_flag_is_a_usage_error(valid_vault):
    result = run_validator(valid_vault, "--unsupported-option")
    assert result.returncode == 2
    assert "usage" in result.stderr.lower()
