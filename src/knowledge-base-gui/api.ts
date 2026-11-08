// Validate the real graph and curator activity responses at the browser boundary.
import type { ActivityEvent, GraphSnapshot, NoteContent } from './types';

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function text(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

function ids(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(text);
}

export function parseActivityEvent(value: unknown): ActivityEvent {
  if (!record(value)
    || !['run_started', 'activity', 'run_finished', 'run_failed', 'graph_changed'].includes(String(value.type))
    || !text(value.run_id) || !text(value.name)
    || typeof value.color !== 'string' || !/^#[\da-f]{6}$/i.test(value.color)
    || typeof value.message !== 'string'
    || !['working', 'done', 'failed'].includes(String(value.status))
    || !ids(value.node_ids) || !ids(value.edge_ids)
    || !text(value.timestamp) || !Number.isFinite(Date.parse(value.timestamp))
    || (value.action !== undefined && (typeof value.action !== 'string' || !['search', 'read', 'traverse', 'spec', 'publish'].includes(value.action)))
    || (value.target_node_id !== undefined && !text(value.target_node_id))
    || (value.run_kind !== undefined && (typeof value.run_kind !== 'string' || !['context', 'update'].includes(value.run_kind)))
    || (value.publication !== undefined && (!record(value.publication)
      || typeof value.publication.status !== 'string' || !['updated', 'unchanged', 'needs_information'].includes(value.publication.status)
      || !Array.isArray(value.publication.notes)
      || !value.publication.notes.every((note) => record(note)
        && typeof note.action === 'string' && ['created', 'updated', 'archived'].includes(note.action) && text(note.path)
        && (note.note_id === undefined || text(note.note_id)) && (note.title === undefined || text(note.title)))))) {
    throw new Error('The activity stream returned an invalid curator event.');
  }
  return value as unknown as ActivityEvent;
}

export async function fetchGraph(signal?: AbortSignal): Promise<GraphSnapshot> {
  const response = await fetch('/api/graph', { signal });
  if (!response.ok) throw new Error(`Graph request failed (${response.status}).`);
  const value: unknown = await response.json();
  if (!record(value) || !text(value.project_id) || !Array.isArray(value.nodes) || !Array.isArray(value.edges)
    || !value.nodes.every((node) => record(node) && ['id', 'title', 'type', 'path'].every((key) => text(node[key])))
    || !value.edges.every((edge) => record(edge) && ['id', 'source', 'target'].every((key) => text(edge[key])))) {
    throw new Error('The server returned an invalid graph snapshot.');
  }
  const graph = value as unknown as GraphSnapshot;
  const nodeIds = new Set(graph.nodes.map(({ id }) => id));
  if (nodeIds.size !== graph.nodes.length || new Set(graph.edges.map(({ id }) => id)).size !== graph.edges.length
    || graph.edges.some(({ source, target }) => !nodeIds.has(source) || !nodeIds.has(target))) {
    throw new Error('The server returned inconsistent graph identifiers.');
  }
  return graph;
}

export async function fetchNote(noteId: string, signal?: AbortSignal): Promise<NoteContent> {
  const response = await fetch(`/api/notes/${encodeURIComponent(noteId)}`, { signal });
  if (!response.ok) throw new Error(response.status === 404 ? 'This note is no longer available.' : `Note request failed (${response.status}).`);
  const value: unknown = await response.json();
  if (!record(value) || value.id !== noteId || !['id', 'title', 'type', 'path'].every((key) => text(value[key]))
    || typeof value.markdown !== 'string' || !Number.isInteger(value.revision) || Number(value.revision) < 1
    || (value.status !== undefined && (typeof value.status !== 'string' || !['active', 'archived', 'superseded'].includes(value.status)))
    || !Array.isArray(value.links) || !value.links.every((link) => record(link) && ['id', 'source', 'target'].every((key) => text(link[key])))) {
    throw new Error('The server returned invalid note contents.');
  }
  return value as unknown as NoteContent;
}
