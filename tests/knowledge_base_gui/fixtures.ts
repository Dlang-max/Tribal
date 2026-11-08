// Provide complete backend graph and curator event fixtures for GUI behavior tests.
import type { ActivityEvent, GraphSnapshot, NoteContent } from '@gui/types';

export const START = Date.parse('2026-11-07T12:00:00.000Z');
export const graph: GraphSnapshot = {
  project_id: 'project-live',
  nodes: [
    { id: 'note-a', title: 'Storage decision', type: 'decision', path: 'decisions/storage.md' },
    { id: 'note-b', title: 'Repository guide', type: 'guide', path: 'guides/repository.md' },
    { id: 'note-c', title: 'Published finding', type: 'finding', path: 'findings/published.md' },
  ],
  edges: [
    { id: 'link-ab', source: 'note-a', target: 'note-b' },
    { id: 'link-bc', source: 'note-b', target: 'note-c' },
  ],
};

export function event(overrides: Partial<ActivityEvent> = {}): ActivityEvent {
  return {
    type: 'activity', run_id: 'run-ada', name: 'Ada curator', color: '#a67aff',
    message: 'Reading storage decision', status: 'working',
    node_ids: ['note-a'], edge_ids: [], timestamp: new Date(START).toISOString(),
    ...overrides,
  };
}

export function noteContent(id = 'note-a'): NoteContent {
  const note = graph.nodes.find((node) => node.id === id)!;
  return { ...note, revision: 1, links: graph.edges.filter((edge) => edge.source === id),
    markdown: `---
title: ${note.title}
status: current
---
# ${note.title}

Actual Markdown body with **shared context** and [reference](https://example.com/docs).

## Summary

- First item
- Second item

1. Ordered item
2. Another item

- [x] Reviewed
- [ ] Follow up

| Note | State | Owner | Revision |
| --- | --- | --- | --- |
| Storage | Ready | Ada | 1 |

> Keep the knowledge connected.

Inline code: \`[[guides/repository]]\`.

\`\`\`js
const note = "[[guides/repository]]";
const longLine = "${'long-code-'.repeat(40)}";
\`\`\`

Read [[guides/repository|Repository details]] or [[missing/note]].

[Unsafe link](javascript:alert%281%29)

<script>window.tribalUnsafe = true</script>
` };
}
