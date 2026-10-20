---
tribal_base_revision: "10000000-0000-4000-8000-000000000010"
schema_version: 1
id: "00000000-0000-4000-8000-000000000010"
title: "Two source trees"
knowledge_base: "fixture-kb"
domain: "authentication"
kind: "overview"
summary: "A synthetic note working across two explicitly identified Git resources."
contexts:
  - key: application
    type: git_repository
    locator: "https://example.org/application.git"
    details:
      commit: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  - key: library
    type: git_repository
    locator: "https://example.org/library.git"
    details:
      branch: main
sources:
  - type: code
    locator: "src/auth.ts"
    context: application
  - type: code
    locator: "lib/identity.ts"
    context: library
    revision: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
---

# Two source trees

The fictional application and library are distinct working contexts within
one knowledge domain. Neither repository owns this knowledge base.
