---
schema_version: 1
id: "00000000-0000-4000-8000-000000000003"
title: "Startup"
tribal_base_revision: 10000000-0000-4000-8000-000000000999
knowledge_base: "fixture-kb"
domain: "authentication"
kind: "procedure"
summary: "Updated synthetic startup summary after a metadata edit."
verification_state: "verified"
verified_at: "2026-10-20T12:00:00Z"
verified_by: "fixture-reviewer"
contexts:
  - key: application-source
    type: git_repository
    locator: "https://example.org/unrelated-service.git"
    details:
      branch: main
      commit: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
sources:
  - type: "test"
    locator: "tests/test_startup.py"
    context: application-source
    revision: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    section: "Initialization"
    details:
      command: "example-test-runner startup-order"
      outcome: "passed"
---

# Startup

## Initialization

This synthetic example records a verification assertion, not a test
executed by this fixture package. Database initialization precedes auth.

| Component | Reference |
|---|---|
| Database | [[database/Setup\|Connection setup]] |

The diagram shows that startup ordering.

```mermaid
flowchart LR
    Database[Initialize database] --> Auth[Initialize authentication]
```

```typescript
// [[Not a link]] is literal example text.
await connectDatabase();
await initializeAuth();
```

## Related knowledge

- [[Setup]]
- [[Guide]]
- [Root guide](../Guide.md)
- [[database/Guide]]
- [[database/Setup#Initialization|Setup details]]
