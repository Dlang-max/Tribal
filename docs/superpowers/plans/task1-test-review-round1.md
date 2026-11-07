# Task 1 test review — round 1

## TEST SPEC

Reviewed the Task 1 plan, test report, implementation report, tests under
`tests/task1/`, and the relevant Task 1 source. The plan calls for meaningful
authentication denial coverage and safe project isolation; it does not require
live GitHub, Kubernetes, Docker, or deployment checks for this task.

The test suite exercises the FastAPI/FastMCP ASGI application in-process.
GitHub's access-token verifier and management OAuth exchange / `/user` response
are faked. The report correctly says that no live GitHub login or deployed
worker was exercised. No test assertion claims otherwise.

## TEST QUALITY

**TEST QUALITY GREEN LIGHT: withheld pending the finding below.**

The tests are generally meaningful: they exercise actual app routes, inspect
returned identity/context and OAuth metadata, deny anonymous and nonmember
requests, verify session-cookie flags and tampering, and cover CSRF acceptance
and rejection. The mocks are at the external GitHub boundary, and the report
states those limits. I found no tautological security assertion.

### Finding — project-to-project token isolation is not tested

`tests/task1/test_project_worker_http_contract.py:29-46` replaces
`GitHubProvider.verify_token` with a verifier that maps a fixture token to a
GitHub subject, without modeling or checking the token's project resource or
audience. The HTTP tests at lines 70-154 build only one project's worker.
`tests/task1/test_project_worker_contract.py:26-42` constructs two context
objects directly, so it does not exercise a token, route, or worker boundary.

As a result, there is no assertion that a credential issued for project A is
rejected by project B, despite project isolation being a stated Task 1 test
criterion. This is a coverage gap, not a claim that the implementation accepts
cross-project credentials: the current suite delegates token verification to a
fake and cannot establish that behavior.

Suggested focused check: configure two worker apps with distinct project IDs,
have the test verifier represent a valid token/resource for A, then assert the
request to B is denied before context is returned. Keep the test report clear
that provider/token cryptography remains mocked.

## Verification performed

Ran `.venv/bin/pytest -q tests/task1` from the repository root:

```text
21 passed in 2.07s
```

No source or test files were changed.
