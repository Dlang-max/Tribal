# Task 4 test review — round 2

## Verdict

**TEST SPEC/QUALITY: WITHHOLD GREEN LIGHT on one narrow packaging assertion gap.** The round-one concurrency defect is fixed: the wheel test builds from a temporary source copy, and a fresh run passed. The built wheel contains all current Python modules and the HTML template. However, the automated archive assertions check only `tribal/templates/projects.html` and its marker; they would still pass if package discovery stopped including the runtime modules. Add an assertion for representative runtime module paths (at minimum `tribal/application.py`) alongside the HTML check.

## Evidence

- Read the round-one review, Task 4 test report, current assembly tests, implementation report, and second-round code review.
- Ran `.venv/bin/pytest -q tests/task4/test_application_assembly.py`: **7 passed**, with three existing FastAPI `router.on_event` deprecation warnings.
- Confirmed the packaging test copies `src/`, `pyproject.toml`, and `requirements.txt` into a fresh pytest temporary directory, builds the wheel there, and reads the resulting archive. The source copy is sufficient for this project's setuptools build configuration and excludes the checkout's shared `build/` directory and egg-info state.
- Independently repeated the isolated-copy build and inspected its archive. It contains `tribal/__init__.py`, `tribal/__main__.py`, `tribal/application.py`, `tribal/authentication.py`, `tribal/kubernetes_provisioner.py`, `tribal/project_management.py`, `tribal/project_store.py`, `tribal/project_worker.py`, `tribal/settings.py`, and `tribal/templates/projects.html`. This confirms the current artifact is complete; the current test does not lock in the module inclusion.
- Reviewed the CLI additions: worker mode is exercised with a captured Uvicorn invocation and checks host/port plus live in-process metadata routes; subprocess coverage checks that both CLI modes fail on missing configuration. These match current CLI behavior.

## Remaining test change

Assert at least `tribal/application.py` (and preferably `tribal/__main__.py`) in `wheel.namelist()` in `test_wheel_contains_management_html_template`. Keep the current template path and marker assertions. This closes the only found gap and prevents a metadata/template-only artifact from satisfying the wheel test.

## Scope and limits

The management assembly, auth/session boundary, project creation and persistence, lifespan reconciliation, worker metadata, environment wiring, and missing-configuration behavior remain covered as described in round one. This review verifies isolated local packaging and in-process app behavior only; it does not establish live OAuth, Kubernetes, Docker, or Codex connectivity. No source or test files were changed.
