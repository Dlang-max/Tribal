---
tribal_base_revision: "10000000-0000-4000-8000-000000000009"
schema_version: 1
id: "00000000-0000-4000-8000-000000000009"
title: "Local configuration"
knowledge_base: "fixture-kb"
domain: "authentication"
kind: "reference"
summary: "A synthetic code reference in an explicitly unversioned folder."
contexts:
  - key: local-files
    type: filesystem
    locator: "file:///srv/unversioned-service"
sources:
  - type: code
    locator: "config/auth.json"
    context: local-files
    revision: "configuration-edition-2026-10"
---

# Local configuration

This fictional source is a file in an ordinary folder. A code source does
not imply Git, even though another note in this domain declares Git work.
