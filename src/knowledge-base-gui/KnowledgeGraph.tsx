// Render real Markdown notes and independently colored curator visits with React Flow.
import { Background, BaseEdge, Controls, getBezierPath, Handle, MarkerType, Position, ReactFlow,
  type Edge, type EdgeProps, type Node, type NodeProps } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { activeVisits } from './activity';
import type { ActivityState, GraphNode, GraphSnapshot, Visit } from './types';

type VisibleVisit = Visit & { opacity: number };
type NoteData = { note: GraphNode; visits: VisibleVisit[] };
type TrailData = { visits: VisibleVisit[] };

function NoteNode({ id, data }: NodeProps<Node<NoteData>>) {
  return <div className="note-node">
    <Handle type="target" position={Position.Left} />
    <small>{data.note.type}</small><strong>{data.note.title}</strong>
    <div className="node-trails">{data.visits.map((visit) => <span key={visit.run_id}
      data-testid="node-visit" data-target-id={id} data-run-id={visit.run_id} data-color={visit.color} data-opacity={visit.opacity}
      className="visit-dot" style={{ backgroundColor: visit.color, opacity: visit.opacity }} title={`${visit.name} visited this note`} />)}</div>
    <Handle type="source" position={Position.Right} />
  </div>;
}

function CuratorEdge(props: EdgeProps<Edge<TrailData>>) {
  const [path] = getBezierPath(props);
  const visits = props.data?.visits ?? [];
  return <g>
    <BaseEdge id={props.id} path={path} markerEnd={props.markerEnd} style={props.style} interactionWidth={24} />
    {visits.map((visit, index) => {
      const offset = (index - (visits.length - 1) / 2) * 6;
      const [trailPath] = getBezierPath({ ...props, sourceY: props.sourceY + offset, targetY: props.targetY + offset });
      return <path key={visit.run_id} d={trailPath} fill="none" stroke={visit.color} strokeWidth={3}
        opacity={visit.opacity} style={{ opacity: visit.opacity, pointerEvents: 'none' }}
        data-testid="edge-visit" data-target-id={props.id} data-run-id={visit.run_id} data-color={visit.color} data-opacity={visit.opacity}>
        <title>{visit.name} followed this link</title>
      </path>;
    })}
  </g>;
}

const nodeTypes = { note: NoteNode };
const edgeTypes = { curator: CuratorEdge };

export interface KnowledgeGraphProps {
  graph: GraphSnapshot;
  activity: ActivityState;
  now: number;
  onSelect: (id: string) => void;
  selectedId?: string;
  query?: string;
  noteType?: string;
}

export function KnowledgeGraph({ graph, activity, now, onSelect, selectedId, query = '', noteType = 'all' }: KnowledgeGraphProps) {
  const search = query.trim().toLowerCase();
  const nodes: Node<NoteData>[] = graph.nodes.flatMap((note, index) => {
    if ((noteType !== 'all' && note.type !== noteType)
      || (search && !`${note.id} ${note.title} ${note.type} ${note.path}`.toLowerCase().includes(search))) return [];
    return [{ id: note.id, type: 'note', position: { x: (index % 3) * 285, y: Math.floor(index / 3) * 155 },
      data: { note, visits: activeVisits(activity, 'nodes', note.id, now) }, selected: selectedId === note.id,
      ariaLabel: `${note.title}, ${note.type} note`, style: { width: 220 } }];
  });
  const visibleIds = new Set(nodes.map(({ id }) => id));
  const edges: Edge<TrailData>[] = graph.edges.filter(({ source, target }) => visibleIds.has(source) && visibleIds.has(target))
    .map((edge) => ({ ...edge, type: 'curator', data: { visits: activeVisits(activity, 'edges', edge.id, now) },
      markerEnd: { type: MarkerType.ArrowClosed, color: '#82708f' }, style: { stroke: '#82708f', strokeWidth: 1.5 } }));
  return <section className="graph-panel panel" aria-label="Interactive knowledge graph">
    <div className="graph-caption"><span>{nodes.length} notes · {edges.length} links</span><span>Drag to pan · scroll to zoom</span></div>
    <div className="graph-canvas"><ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes}
      fitView fitViewOptions={{ padding: 0.3 }} nodesDraggable={false} nodesConnectable={false} edgesReconnectable={false}
      onNodeClick={(_, node) => onSelect(node.id)} minZoom={0.2} maxZoom={2} colorMode="dark">
      <Background color="#59436c" gap={24} /><Controls showInteractive={false} />
    </ReactFlow>{nodes.length === 0 && <p className="graph-empty">{graph.nodes.length === 0 ? 'The knowledge base has no notes yet.' : 'No notes match these filters.'}</p>}</div>
  </section>;
}
