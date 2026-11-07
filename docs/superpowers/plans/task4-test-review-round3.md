# Task 4 test review — round 3 (final)

## Verdict

**TEST SPEC/QUALITY: GREEN LIGHT.** The round-two packaging gap is closed. The test verifies the built wheel contains all nine runtime modules and the management HTML template, then installs that wheel into a temporary target and runs its CLI from outside the source checkout. No remaining direct test or source regression was found in the reviewed Task 4 scope.

## Evidence

- Read the Task 4 plan, implementation and test reports, both prior Task 4 test reviews, repository guidance, and the relevant Tribal vault architecture, status, and roadmap notes.
- Ran `.venv/bin/pytest -q tests/task4/test_application_assembly.py`: **7 passed**, with three existing FastAPI `router.on_event` deprecation warnings.
- Confirmed the wheel build copies only `src/`, `pyproject.toml`, and `requirements.txt` into a fresh pytest temporary directory, then uses a separate temporary wheelhouse. Its build output cannot collide with the checkout's shared `build/` directory.
- Confirmed archive checks require all nine runtime module paths, `tribal/templates/projects.html`, and the expected CSRF marker.
- Confirmed the test installs that wheel to a fresh temporary target and launches `python -m tribal --help` with the temporary directory as cwd and the installed target at the front of `PYTHONPATH`. The checkout is not on the normal import path for this subprocess, so an editable/source installation cannot silently satisfy the CLI check.
- Reviewed the current CLI and application assembly paths against these assertions. No direct regression affecting the packaging or reviewed assembly claims was found.

## Scope and limits

The coordinating agent reports the full suite at **67 passed** with four known warnings, plus clean `pip check`, `compileall`, and diff checks; this review independently reran the focused Task 4 suite only. Tests remain isolated local checks: they do not establish live GitHub OAuth, Kubernetes provisioning, a Docker image build, or an end-to-end Codex connection.
