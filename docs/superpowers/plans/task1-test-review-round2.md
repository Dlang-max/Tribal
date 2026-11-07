# Task 1 test review — round 2

## TEST SPEC

**TEST SPEC GREEN LIGHT.** The new two-worker HTTP test closes round one's project-isolation coverage gap. It constructs distinct project A and B workers, issues an access token through project A's real FastMCP `JWTIssuer`, then sends that bearer token through both workers' real MCP HTTP authentication paths. A returns project A's context; B rejects the request with HTTP 401 before any tool result is returned. The response is checked for either project ID, and neither is present.

Only the external GitHub upstream token verification is faked: `GitHubTokenVerifier.verify_token` is replaced with a fixture for the stored GitHub credential. FastMCP's JWT signing and validation, worker provider configuration, bearer-auth middleware, route handling, JTI/upstream-token lookup, and HTTP response are exercised normally. The single fake verifier call also confirms B rejects the project A JWT before reaching the external GitHub check. This is not a tautology: token issuance and verification are not stubbed, and the test makes real requests through both ASGI applications.

## TEST QUALITY

**TEST QUALITY GREEN LIGHT.** The positive case asserts the returned structured context belongs to A. The negative case asserts B returns 401 and no project context. The test's setup and assertions do not manufacture the denial in a fixture. Existing Task 1 coverage remains in place.

One scope detail: A and B have different signing keys as well as project-specific issuer and audience URLs. Therefore this test demonstrates rejection under the plan's per-project signing-secret model; it does not isolate the issuer/audience mismatch as the particular reason for rejection. The test report's statement that issuer/audience checks are exercised is broader than this test alone establishes, since B can reject the token on signature validation first. This does not block the required A-accept/B-deny isolation check.

## Verification performed

Ran `.venv/bin/pytest -q tests/task1` from the repository root:

```text
22 passed in 2.17s
```

No implementation or test files were changed. No live GitHub, Kubernetes, Docker, or deployed-worker integration is claimed.
