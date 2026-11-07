# Task 4 test review — round 1

## Verdict

**TEST SPEC/QUALITY: WITHHOLD GREEN LIGHT.** Six assembly tests cover the requested boundaries well, but the packaging test builds directly from the shared repository root. The full-suite run produced a wheel containing only `.dist-info` metadata, so packaging coverage is nondeterministic under concurrent builds and does not currently provide a reliable acceptance check. The app factories, middleware, route registration, handlers, SQLite store, and worker metadata routes are otherwise exercised directly.

## Evidence reviewed

- Approved Task 4 plan, Task 4 implementation and test reports.
- `tests/task4/test_application_assembly.py` and relevant assembly, settings, and project-management source.
- Existing Task 2/3 test reports to distinguish coverage already reviewed there.
- Reran `.venv/bin/pytest -q tests/task4`: **7 passed** in isolation, with 3 expected FastAPI `router.on_event` deprecation warnings. The coordinating agent reported the full suite then had 63 passing tests and one wheel-content failure: the produced archive contained only `.dist-info` files. A serial root build succeeded, consistent with a shared `build/` output race; this review did not repeat builds after that finding.

## Coverage findings

- Management factory test uses an on-disk `ProjectStore` and the real `TestClient` lifespan. It verifies health, registered auth routing, unauthenticated API denial, a signed session cookie rendered by the real session middleware/page route, CSRF-protected project creation, asynchronous provisioning, persisted ready state, owner ID passed to provisioning, and the assembled MCP URL.
- Separate management lifespan test starts the actual assembled app around a persisted incomplete record, then observes startup reconciliation through the store and provisioner.
- Worker test constructs the actual worker factory from environment settings and checks health/readiness plus authorization-server and protected-resource metadata at the project's prefixed discovery paths, including exact public URLs.
- Runtime wiring test calls the actual management factory and captures only `KubernetesProvisioner.from_cluster` arguments. It verifies the configured template root, worker image, and public URL reach the adapter constructor. This complements the Task 2/3 tests of the real provisioner and checked-in templates; it is not a mock app factory that bypasses route wiring.
- Missing settings are rejected by management construction; a subprocess exercises `python -m tribal management` and verifies nonzero exit with the missing-configuration error.
- Packaging test invokes a real local wheel build and inspects the archive for the management HTML and its CSRF template marker, but builds from the shared repository tree. An observed full-suite run returned a validly named wheel with only `.dist-info` contents, making this test flaky when another build mutates the shared setuptools output directory.

## Required test-review fix

Build the wheel from an isolated temporary copy of the source tree (or otherwise give the build a unique output directory) so concurrent builds cannot share and truncate `build/lib`. Keep inspecting the actual resulting archive for both the template and its marker. The observed metadata-only wheel is a material failure of the Task 4 packaged-template acceptance check. After the test fix, rerun the full suite and ensure the archive-content assertion passes under the same concurrent conditions that exposed the failure.

A smaller coverage note: the management app test directly asserts `/healthz`, while `/readyz` delegates to that same handler and is not independently requested in this suite. Worker `/readyz` is asserted. This is not the blocking finding.

## Limits

The fake provisioner does not establish live Kubernetes provisioning. The configuration wiring test verifies the configured template root is passed into the real adapter constructor boundary, while Task 3 tests separately exercise rendering from the actual template tree. No Docker build, live cluster, OAuth exchange, or Codex connection is claimed.
