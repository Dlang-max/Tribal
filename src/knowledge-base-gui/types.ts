// Wire contracts and transient curator overlays for the Markdown knowledge graph.
export interface GraphNode { id: string; title: string; type: string; path: string }
export interface GraphEdge { id: string; source: string; target: string }
export interface GraphSnapshot { project_id: string; nodes: GraphNode[]; edges: GraphEdge[] }
export type CuratorAction = 'search' | 'read' | 'traverse' | 'spec' | 'publish';
export interface PublicationNote { action: 'created' | 'updated' | 'archived'; path: string; note_id?: string; title?: string }
export interface Publication { status: 'updated' | 'unchanged' | 'needs_information'; notes: PublicationNote[] }
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
  action?: CuratorAction;
  target_node_id?: string;
  run_kind?: 'context' | 'update';
  publication?: Publication;
}
export interface RunActivity extends ActivityEvent {
  observed_node_ids?: string[];
  observed_edge_ids?: string[];
  lastRead?: ActivityEvent;
  publicationEvent?: ActivityEvent;
  receipts?: (PublicationNote & { timestamp: string })[];
}
export interface Visit { run_id: string; name: string; color: string; timestamp: number; action?: CuratorAction; target_node_id?: string }
export interface ActivityState {
  runs: Record<string, RunActivity>;
  nodes: Record<string, Record<string, Visit>>;
  edges: Record<string, Record<string, Visit>>;
}
export interface NoteContent extends GraphNode { markdown: string; revision: number; links: GraphEdge[]; status?: 'active' | 'archived' | 'superseded' }
