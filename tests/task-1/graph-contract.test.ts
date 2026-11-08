// Verify shared graph records represent the sample project contract.
import type { ProjectGraph } from '@/shared';

describe('shared graph contract', () => {
  it('supports project scoped entities and UI edge identities separate from domain relationships', () => {
    const graph = {
      id: 'project-tribal',
      name: 'Tribal',
      description: 'Illustrative local project graph.',
      entities: [
        {
          id: 'repository-tribal',
          kind: 'object',
          type: 'Repository',
          label: 'Tribal repository',
          fields: {
            description: 'Shared context for agents and repositories.',
            url: 'https://example.com/tribal',
            metadata: { language: 'TypeScript', archived: false },
          },
        },
        {
          id: 'event-commit',
          kind: 'event',
          type: 'ChangeCommitted',
          label: 'Initial commit',
          fields: {
            description: 'A repository change was committed.',
            timestamp: '2026-11-07T14:30:00Z',
          },
        },
      ],
      relationships: [
        {
          id: 'edge-commit-repository',
          type: 'OccurredIn',
          relationship: { source: 'event-commit', target: 'repository-tribal' },
        },
      ],
    } satisfies ProjectGraph;

    const relationship = graph.relationships[0];
    const endpoints = new Set(graph.entities.map(({ id }) => id));

    expect(endpoints.has(relationship.relationship.source)).toBe(true);
    expect(endpoints.has(relationship.relationship.target)).toBe(true);
    expect(relationship.id).toBe('edge-commit-repository');
    expect(relationship.type).toBe('OccurredIn');
    expect(Object.keys(relationship.relationship).sort()).toEqual(['source', 'target']);
    expect(graph.entities[0].fields).not.toHaveProperty('id');
    expect(graph.entities[1].fields.timestamp).toBe('2026-11-07T14:30:00Z');
  });
});
