# Shared frontend contracts

Import shared types and helpers from `@/shared`. The `@/` alias resolves to
`src/` in TypeScript, Vite, and Vitest.

## Navigation

`NAVIGATION_ITEMS` defines the ordered local pages and labels. `NavigationId`
is the union `overview | repositories | agents-tasks | knowledge-explorer |
settings`. The shell owns active-page state; the IDs do not imply URLs or a
backend router.

## Knowledge graph

`ProjectGraph` contains `id`, `name`, `description`, `entities`, and
`relationships`. Each project supplies its complete scoped graph explicitly.
These are local illustrative records, not a finalized backend schema.

`GraphEntity` is an object/event discriminated union:

```ts
const repository: GraphEntity = {
  id: 'repository-tribal',
  kind: 'object',
  type: 'Repository',
  label: 'Tribal',
  fields: {
    description: 'Illustrative repository record.',
    name: 'Tribal',
    url: 'https://example.com/tribal',
  },
};
```

Entity `id` is the inherited ontology field and must uniquely address either
an Object or Event within its project. `fields` contains the inherited
`description`, the required `timestamp` for Events, and additional subclass
fields. Render the complete inspector fields as `{ id: entity.id,
...entity.fields }`; do not duplicate `id` inside `fields`. `label`, `kind`, and
`type` describe the representation and subclass; do not add them as inherited
domain fields. `FieldValue` supports JSON scalars, null, arrays, and nested
objects so the inspector can render fields without hardcoding subclasses.

`GraphRelationship` holds `{ id, type, relationship }`. Its `id` is a UI-only
edge identity and `type` is the subclass label. The nested `relationship`
contains **only** `{ source, target }`, referencing entity IDs in the same
project. Pass the outer `id` to React Flow; inspect the two inner fields as the
domain relationship. Do not mutate records to store selection or layout.

The explorer owns sample graphs, selection, filtering, and node positions.
Changing projects clears project-specific selection and filters. The shell
accepts an optional `knowledgeExplorer` React node; the entry point will wire
that feature during integration.

## Styling

`cn` combines `clsx` with `tailwind-merge`. Tailwind v4 runs through the Vite
plugin; the theme entry point should import `tailwindcss`. `components.json`
points shadcn tools at `src/theme/index.css` and `@/components/ui`. Controls
should use the theme's conventional shadcn variables.
