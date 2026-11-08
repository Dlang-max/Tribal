// Validate the real graph and curator activity responses at the browser boundary.
import type { ActivityEvent, GraphSnapshot } from './types';

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
    || !text(value.timestamp) || !Number.isFinite(Date.parse(value.timestamp))) {
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
