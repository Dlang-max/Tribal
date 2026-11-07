# Task 1 test report

## Scope

Behavioral tests for Task 1 settings, GitHub management authentication, and
project worker contracts. Tests are in `tests/task1/`.

## Verification

Command:

```text
.venv/bin/pytest -q tests/task1
```

Result:

```text
....................                                                     [100%]
22 passed in 2.18s
```

The tests cover environment validation and normalization, GitHub callback
identity derived from the fake upstream `/user` response's numeric ID, invalid
upstream identities, signed session cookie properties and tampering, CSRF
acceptance and denial, anonymous request denial, project-specific sample
context, worker and management-only settings, rejection of unsupported public URL path prefixes, worker health/readiness, OAuth metadata resource and issuer values,
unauthenticated MCP denial, JSON stateless MCP responses, and member versus
nonmember tool access. Repeated MCP calls confirm the token verifier is invoked
for each request. A separate two-worker test issues a project A JWT with
FastMCP's `JWTIssuer`, seeds its normal JTI/upstream-token records, confirms A
accepts it, and confirms B rejects it before returning context. The workers
have distinct signing keys, issuer URLs, and audience URLs.

## Limits

GitHub OAuth exchange and the upstream `/user` identity response are not live.
The cross-project test uses FastMCP's real JWT signing and validation, route
authentication, audience/issuer checks, and token stores, while faking only the
upstream GitHub token check. Other focused membership cases inject a verified
token fixture directly. The full browser OAuth authorization/token flow,
Kubernetes, ingress proxy behavior, Docker, and a deployed worker remain outside
this test run. Metadata and tool requests were exercised in-process through
FastMCP's ASGI app.
