// Maintain independently fading visits for every server-side curator run.
import type { ActivityEvent, ActivityState, Visit } from './types';
export const FADE_MS = 10_000;
export function emptyActivityState(): ActivityState { return { runs: {}, nodes: {}, edges: {} }; }

export function applyActivityEvent(state: ActivityState, event: ActivityEvent): ActivityState {
  const timestamp = Date.parse(event.timestamp);
  if (!Number.isFinite(timestamp)) return state;
  const visit = { run_id: event.run_id, name: event.name, color: event.color, timestamp };
  const next = { ...state, nodes: { ...state.nodes }, edges: { ...state.edges } };
  const previous = Object.hasOwn(state.runs, event.run_id) ? state.runs[event.run_id] : undefined;
  if (!previous || Date.parse(previous.timestamp) <= timestamp) {
    next.runs = { ...state.runs, [event.run_id]: event };
  }
  for (const kind of ['nodes', 'edges'] as const) {
    for (const id of kind === 'nodes' ? event.node_ids : event.edge_ids) {
      const visits = Object.hasOwn(state[kind], id) ? state[kind][id] : {};
      const old = Object.hasOwn(visits, event.run_id) ? visits[event.run_id] : undefined;
      if (!old || old.timestamp <= timestamp) next[kind][id] = { ...visits, [event.run_id]: visit };
    }
  }
  return next;
}

export function activeVisits(state: ActivityState, kind: 'nodes' | 'edges', id: string, now: number): (Visit & {opacity: number})[] {
  if (!Object.hasOwn(state[kind], id)) return [];
  return Object.values(state[kind][id])
    .map((visit) => ({ ...visit, opacity: Math.max(0, Math.min(1, 1 - (now - visit.timestamp) / FADE_MS)) }))
    .filter(({ opacity }) => opacity > 0)
    .sort((a, b) => a.run_id.localeCompare(b.run_id));
}

export function pruneActivity(state: ActivityState, now: number): ActivityState {
  const pruneVisits = (kind: 'nodes' | 'edges') => Object.fromEntries(Object.keys(state[kind])
    .map((id) => [id, Object.fromEntries(activeVisits(state, kind, id, now).map(({ opacity: _, ...visit }) => [visit.run_id, visit]))] as const)
    .filter(([, visits]) => Object.keys(visits).length > 0));
  const runs = Object.values(state.runs).sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp));
  const recentCompleted = new Set(runs.filter(({ status }) => status !== 'working').slice(0, 20).map(({ run_id }) => run_id));
  return {
    runs: Object.fromEntries(runs.filter((run) => run.status === 'working' || recentCompleted.has(run.run_id)
      || now - Date.parse(run.timestamp) < FADE_MS).map((run) => [run.run_id, run])),
    nodes: pruneVisits('nodes'), edges: pruneVisits('edges'),
  };
}
