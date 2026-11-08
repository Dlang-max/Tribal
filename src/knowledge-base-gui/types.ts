// Wire contracts and transient curator overlays for the Markdown knowledge graph.
export interface GraphNode { id: string; title: string; type: string; path: string }
export interface GraphEdge { id: string; source: string; target: string }
export interface GraphSnapshot { project_id: string; nodes: GraphNode[]; edges: GraphEdge[] }
export interface ActivityEvent {
  type: 'run_started' | 'activity' | 'run_finished' | 'run_failed' | 'graph_changed';
  run_id: string;
  name: string;
  color: string;
  message: string;
  status: 'working' | 'done' | 'failed';
  node_ids: string[];
  edge_ids: string[];
  timestamp: string;
}
export type RunActivity = ActivityEvent;
export interface Visit { run_id: string; name: string; color: string; timestamp: number }
export interface ActivityState {
  runs: Record<string, RunActivity>;
  nodes: Record<string, Record<string, Visit>>;
  edges: Record<string, Record<string, Visit>>;
}
