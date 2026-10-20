---
tribal_base_revision: "10000000-0000-4000-8000-000000000012"
schema_version: 1
id: "00000000-0000-4000-8000-000000000012"
title: "Custom survey"
knowledge_base: "fixture-kb"
domain: "botany"
kind: "finding"
summary: "An extensible non-Git context and source profile."
contexts:
  - key: community-records
    type: community_survey
    locator: "urn:example:community-records"
sources:
  - type: field_record
    locator: "record:sample-7"
    context: community-records
    revision: "edition-two"
---

# Custom survey

This fictional profile demonstrates preservation of unfamiliar context and
source types. Their semantics are unchecked; no Git hash rules apply.
