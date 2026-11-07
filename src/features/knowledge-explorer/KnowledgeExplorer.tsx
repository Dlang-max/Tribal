import { useMemo, useState } from 'react';
import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type { GraphEntity, ProjectGraph } from '@/shared/graph';
import './knowledge-explorer.css';

const sampleProjects: ProjectGraph[] = [
  {
    id: 'tribal-platform',
    name: 'Tribal Platform',
    description: 'Illustrative context for a shared agent memory platform.',
    entities: [
      { id: 'repo-tribal', kind: 'object', type: 'Repository', label: 'Tribal repository', fields: { description: 'Application source and project documentation.', name: 'tribal', url: 'https://github.com/example/tribal' } },
      { id: 'agent-codex', kind: 'object', type: 'Agent', label: 'Codex sample agent', fields: { description: 'An illustrative agent identity for this sample project.', name: 'Codex sample agent', sessionId: 'example-session-001' } },
      { id: 'task-graph', kind: 'object', type: 'WorkItem', label: 'Knowledge explorer', fields: { description: 'Build an inspection view for project context.', title: 'Knowledge explorer', status: 'in_progress' } },
      { id: 'event-design', kind: 'event', type: 'WorkStarted', label: 'Knowledge explorer work began', fields: { description: 'Illustrative occurrence: work on the Knowledge Explorer began.', timestamp: '2026-11-07T14:30:00-05:00' } },
      { id: 'evidence-ontology', kind: 'object', type: 'Evidence', label: 'Ontology reference', fields: { description: 'Sample supporting material about the project context vocabulary.' } },
    ],
    relationships: [
      { id: 'tribal-r1', type: 'References', relationship: { source: 'evidence-ontology', target: 'repo-tribal' } },
      { id: 'tribal-r2', type: 'WorksOn', relationship: { source: 'agent-codex', target: 'task-graph' } },
      { id: 'tribal-r3', type: 'About', relationship: { source: 'event-design', target: 'task-graph' } },
      { id: 'tribal-r4', type: 'PerformedBy', relationship: { source: 'event-design', target: 'agent-codex' } },
    ],
  },
  {
    id: 'field-notes',
    name: 'Field Notes',
    description: 'Illustrative context for a small research project.',
    entities: [
      { id: 'repo-notes', kind: 'object', type: 'Repository', label: 'Field notes repo', fields: { description: 'A sample repository for collecting observations.', name: 'field-notes', url: 'https://github.com/example/field-notes' } },
      { id: 'person-maya', kind: 'object', type: 'Developer', label: 'Maya Chen (sample identity)', fields: { description: 'Synthetic identity values used only to illustrate a Developer record.', firstName: 'Maya', lastName: 'Chen', email: 'maya.chen@example.org' } },
      { id: 'finding-pollinator', kind: 'object', type: 'Finding', label: 'Pollinator activity', fields: { description: 'Illustrative finding: monarch butterflies visited the sample garden.' } },
      { id: 'evidence-garden', kind: 'object', type: 'Evidence', label: 'Garden observation notes', fields: { description: 'Synthetic observation notes that support the pollinator finding.', sourceUri: 'https://example.org/field-notes/pollinator-observation' } },
    ],
    relationships: [
      { id: 'notes-r1', type: 'About', relationship: { source: 'finding-pollinator', target: 'repo-notes' } },
      { id: 'notes-r2', type: 'Supports', relationship: { source: 'evidence-garden', target: 'finding-pollinator' } },
      { id: 'notes-r3', type: 'ProducedBy', relationship: { source: 'finding-pollinator', target: 'person-maya' } },
      { id: 'notes-r4', type: 'References', relationship: { source: 'evidence-garden', target: 'repo-notes' } },
    ],
  },
];

type Selection = { kind: 'entity'; id: string } | { kind: 'relationship'; id: string } | null;
type Filter = 'all' | 'object' | 'event';

function searchableEntity(entity: GraphEntity) {
  return `${entity.id} ${entity.type} ${entity.label} ${JSON.stringify(entity.fields)}`.toLowerCase();
}

function FieldRows({ fields }: { fields: object }) {
  return <dl className="ke-field-list">{Object.entries(fields).map(([name, value]) => <div className="ke-field" key={name}><dt>{name}</dt><dd>{typeof value === 'object' && value !== null ? <pre>{JSON.stringify(value, null, 2)}</pre> : String(value)}</dd></div>)}</dl>;
}

export function KnowledgeExplorer() {
  const [projectId, setProjectId] = useState(sampleProjects[0].id);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<Filter>('all');
  const [selection, setSelection] = useState<Selection>(null);
  const project = sampleProjects.find((candidate) => candidate.id === projectId) ?? sampleProjects[0];

  const visibleEntities = useMemo(() => project.entities.filter((entity) => {
    const matchesKind = filter === 'all' || entity.kind === filter;
    return matchesKind && (!query.trim() || searchableEntity(entity).includes(query.trim().toLowerCase()));
  }), [filter, project, query]);
  const visibleIds = new Set(visibleEntities.map((entity) => entity.id));
  const visibleRelationships = project.relationships.filter(({ relationship }) => visibleIds.has(relationship.source) && visibleIds.has(relationship.target));
  const selectedEntity = selection?.kind === 'entity' ? project.entities.find(({ id }) => id === selection.id) : undefined;
  const selectedRelationship = selection?.kind === 'relationship' ? project.relationships.find(({ id }) => id === selection.id) : undefined;
  const entityById = new Map(project.entities.map((entity) => [entity.id, entity]));

  const nodes: Node[] = visibleEntities.map((entity, index) => ({
    id: entity.id,
    position: { x: (index % 3) * 240, y: Math.floor(index / 3) * 150 },
    data: { kind: entity.kind, label: <span className={`ke-node ke-node-${entity.kind}`}><small>{entity.kind === 'object' ? 'Object' : 'Event'} · {entity.type}</small><strong>{entity.label}</strong></span> },
    className: selection?.kind === 'entity' && selection.id === entity.id ? 'ke-node-selected' : '',
    style: { background: '#251833', color: '#F4F0FA', border: `1px solid ${entity.kind === 'event' ? '#A67AFF' : '#59436c'}`, borderRadius: 12, padding: 0, width: 190, overflow: 'hidden' },
  }));
  const edges: Edge[] = visibleRelationships.map((edge) => ({
    id: edge.id,
    source: edge.relationship.source,
    target: edge.relationship.target,
    label: edge.type,
    animated: selection?.kind === 'relationship' && selection.id === edge.id,
    markerEnd: { type: MarkerType.ArrowClosed, color: '#A67AFF' },
    style: { stroke: '#A67AFF', strokeWidth: 1.5 },
    labelStyle: { fill: '#C6BBD3', fontSize: 11 },
    labelBgStyle: { fill: '#100B18', fillOpacity: 0.9 },
  }));

  function changeProject(nextId: string) {
    setProjectId(nextId);
    setSelection(null);
    setFilter('all');
    setQuery('');
  }

  return <main className="knowledge-explorer">
    <header className="ke-header">
      <div><p className="ke-eyebrow">Knowledge base · illustrative sample data</p><h1>Knowledge explorer</h1><p className="ke-project-description">{project.description}</p></div>
      <label className="ke-project-picker">Project<select aria-label="Choose project" value={projectId} onChange={(event) => changeProject(event.target.value)}>{sampleProjects.map(({ id, name }) => <option key={id} value={id}>{name}</option>)}</select></label>
    </header>
    <div className="ke-layout">
      <aside className="ke-browse" aria-label="Graph browser">
        <label className="ke-search">Search entities<input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Name, type, or field…" /></label>
        <fieldset className="ke-filters"><legend>Entity type</legend>{(['all', 'object', 'event'] as const).map((value) => <label key={value}><input type="radio" name="entity-type" value={value} checked={filter === value} onChange={() => setFilter(value)} />{value === 'all' ? 'All' : `${value[0].toUpperCase()}${value.slice(1)}s`}</label>)}</fieldset>
        <section className="ke-list-section"><h2>Entities <span>{visibleEntities.length}</span></h2><ul className="ke-entity-list">{visibleEntities.map((entity) => <li key={entity.id}><button type="button" aria-pressed={selection?.kind === 'entity' && selection.id === entity.id} onClick={() => setSelection({ kind: 'entity', id: entity.id })}><span className="ke-kind-dot" aria-hidden="true">{entity.kind === 'object' ? 'O' : 'E'}</span><span><strong>{entity.label}</strong><small>{entity.type}</small></span></button></li>)}</ul>{visibleEntities.length === 0 && <p className="ke-empty">No entities match this search.</p>}</section>
        <section className="ke-list-section ke-relation-list"><h2>Relationships <span>{visibleRelationships.length}</span></h2><ul className="ke-entity-list">{visibleRelationships.map((edge) => <li key={edge.id}><button type="button" aria-pressed={selection?.kind === 'relationship' && selection.id === edge.id} onClick={() => setSelection({ kind: 'relationship', id: edge.id })}><span className="ke-kind-dot ke-relation-dot" aria-hidden="true">↗</span><span><strong>{edge.type}</strong><small>{entityById.get(edge.relationship.source)?.label} → {entityById.get(edge.relationship.target)?.label}</small></span></button></li>)}</ul>{visibleRelationships.length === 0 && <p className="ke-empty">No relationships between these entities.</p>}</section>
      </aside>
      <section className="ke-graph-panel" aria-label="Interactive knowledge graph"><div className="ke-graph-caption"><span>Interactive graph</span><span>Drag to pan · scroll to zoom</span></div><div className="ke-canvas"><ReactFlow key={project.id} nodes={nodes} edges={edges} fitView fitViewOptions={{ padding: 0.25 }} nodesDraggable={false} nodesConnectable={false} edgesReconnectable={false} elementsSelectable onNodeClick={(_, node) => setSelection({ kind: 'entity', id: node.id })} onEdgeClick={(_, edge) => setSelection({ kind: 'relationship', id: edge.id })} onPaneClick={() => setSelection(null)} minZoom={0.25} maxZoom={1.8}><Background color="#59436c" gap={24} /><Controls showInteractive={false} /><MiniMap nodeColor={(node) => node.data.kind === 'event' ? '#A67AFF' : '#59436c'} maskColor="rgba(9, 8, 13, 0.7)" style={{ width: 110, height: 80, backgroundColor: '#251833', border: '1px solid #59436c' }} /></ReactFlow></div></section>
      <aside className="ke-inspector" aria-label="Selection details"><p className="ke-eyebrow">Inspector</p>{selectedEntity ? <><h2>{selectedEntity.label}</h2><p className="ke-inspector-type">{selectedEntity.kind === 'object' ? 'Object' : 'Event'} · {selectedEntity.type}</p><p className="ke-record-id">{selectedEntity.id}</p><h3>Fields</h3><FieldRows fields={selectedEntity.fields} /><h3>Connections</h3><ul className="ke-connection-list">{project.relationships.filter((edge) => edge.relationship.source === selectedEntity.id || edge.relationship.target === selectedEntity.id).map((edge) => { const outgoing = edge.relationship.source === selectedEntity.id; const neighbor = entityById.get(outgoing ? edge.relationship.target : edge.relationship.source); return <li key={edge.id}><span>{outgoing ? 'To' : 'From'} · {edge.type}</span><button disabled={!neighbor} onClick={() => neighbor && setSelection({ kind: 'entity', id: neighbor.id })}><strong>{neighbor?.label ?? 'Unknown entity'}</strong><small>{neighbor?.type ?? 'Missing endpoint'}{neighbor ? ' · select entity' : ' · unavailable'}</small></button><button className="ke-connection-detail" onClick={() => setSelection({ kind: 'relationship', id: edge.id })}>Inspect relationship</button></li>; })}</ul></> : selectedRelationship ? <><h2>{selectedRelationship.type}</h2><p className="ke-inspector-type">Relationship</p><p className="ke-record-id">UI edge · {selectedRelationship.id}</p><h3>Relationship fields</h3><FieldRows fields={selectedRelationship.relationship} /><h3>Endpoints</h3><dl className="ke-endpoints"><div><dt>Source</dt><dd>{entityById.get(selectedRelationship.relationship.source)?.label ?? selectedRelationship.relationship.source}</dd><code>{selectedRelationship.relationship.source}</code></div><div><dt>Target</dt><dd>{entityById.get(selectedRelationship.relationship.target)?.label ?? selectedRelationship.relationship.target}</dd><code>{selectedRelationship.relationship.target}</code></div></dl></> : <div className="ke-inspector-empty"><span aria-hidden="true">⌖</span><h2>Inspect the graph</h2><p>Select an entity or relationship in the graph or browse lists to see its fields here.</p></div>}</aside>
    </div>
    <p className="ke-sample-note">Sample graphs are illustrative and do not represent live project data.</p>
  </main>;
}

export default KnowledgeExplorer;
