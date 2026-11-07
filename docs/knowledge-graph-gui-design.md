# Tribal knowledge graph GUI — proposed first version

Status: proposed for review, 2026-11-07. This document proposes the first local GUI; it does not record approval of a technology, field schema, or storage implementation.

## Purpose

Each Project has a knowledge base defined by Tribal's ontology. Give people a way to explore the context recorded by agents working on that project, see connections across its repositories, and inspect entity fields.

Project scope selects the graph being viewed. It does not require a separate physical database for every project or exclusive repository ownership.

## Approaches

- **Interactive graph with field inspector — recommended:** put relationships at the center of the experience, with project selection, search, type filters, and a panel for entity and connection details. Field inspection remains useful as the ontology evolves.
- **Table-first browser:** easier to scan many records and fields, but connections require extra navigation. A table could be added later as an alternative view.

Manual knowledge-base editing is a separate scope choice awaiting the user's preference. The proposed first version focuses on inspection.

## Proposed screen and behavior

- A project selector switches the displayed knowledge base and clears the previous selection and project-specific search/filter state.
- A left panel provides search and entity-type filters. Search covers IDs, labels, descriptions, and other field values.
- The main area displays entities as nodes and typed, directed relationships as connections. Provide pan, zoom, fit-to-view, and selection. Distinguish Objects and Events using visible text as well as styling.
- Selecting an entity opens a right-side inspector showing its class, inherited fields, additional fields, and incoming/outgoing relationships. Selecting a related entity navigates to it.
- Selecting a connection shows its relationship class and source/target entities. Keep presentation metadata separate from ontology fields; do not add IDs or labels to the ontology's two-field Relationship schema.
- Render fields from data rather than fixing the inspector to a list of subclass properties. Display missing values and nested values clearly, and render imported strings as text.
- Provide usable empty states for an empty project or filters with no matches. All primary navigation and inspection actions must work with a keyboard.

## Data and ontology

Use clearly labeled illustrative project graphs initially because the repository has no knowledge-base service or read API. Keep the data access boundary replaceable for future backend integration. Sample labels, timestamps, session-file paths, and subclass field values are examples, not real agent activity or approval of proposed fields.

Follow the current vault vocabulary: twelve Object subclasses (including AgentSession), four Event subclasses, and twenty-five Relationship subclasses. Object and Event instances have required explicit IDs. The current proposed subclass field schema remains a proposal. References to session files do not import or expose session contents.

Represent project scope explicitly in the data supplied to the viewer. Do not infer the entire project graph solely by traversing HasRepository: a connected repository may be shared by projects, and detailed record-scoping policies remain unresolved.

## Proposed implementation choices

Build a local browser application in this repository, with all application source under `src/`. React with TypeScript is the proposed UI stack. React Flow is a candidate for graph interactions and keyboard navigation; Cytoscape.js is an alternative if automatic network layout takes priority. Final library choice remains with implementation after design review.

Use a restrained desktop workspace with a large graph area, readable type labels, and collapsible panels on smaller screens. This is an application screen, not a marketing page. Keep deployment, database selection, agent ingestion, authentication, and MCP implementation outside this first increment.

## Acceptance and checks

The first version should run locally, switch between at least two illustrative project graphs without leaking selections, support graph navigation and search/filter interactions, and inspect fields and relationship endpoints. Manually check the main interactions, keyboard access, empty results, and narrow layouts. Run the production build. Do not write tests unless explicitly requested, following repository guidance.

## Decisions still needed

- Confirm the graph-and-inspector approach and whether manual editing belongs in the first version.
- Review the first screen, then connect a real project knowledge-base read interface when its contract is available.
