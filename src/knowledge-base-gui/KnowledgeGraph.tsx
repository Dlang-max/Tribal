// Render real Markdown notes and independently colored curator visits with React Flow.
import { createContext, useContext, useEffect } from 'react';
import { Background, BaseEdge, Controls, getBezierPath, Handle, MarkerType, Position, ReactFlow, useNodesState,
  type Edge, type EdgeProps, type Node, type NodeProps } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { activeVisits, emptyActivityState } from './activity';
import type { ActivityState, GraphNode, GraphSnapshot } from './types';

type NoteData = { note: GraphNode };
const VisitContext = createContext({ activity: emptyActivityState(), now: 0 });

function NoteNode({ id, data }: NodeProps<Node<NoteData>>) {
  const { activity, now } = useContext(VisitContext);
  const visits = activeVisits(activity, 'nodes', id, now);
  return <div className="note-node">
    <Handle type="target" position={Position.Left} />
    <small>{data.note.type}</small><strong>{data.note.title}</strong>
    <div className="node-trails">{visits.map((visit) => <span key={visit.run_id}
      data-testid="node-visit" data-target-id={id} data-run-id={visit.run_id} data-color={visit.color} data-opacity={visit.opacity}
      className="visit-dot" style={{ backgroundColor: visit.color, opacity: visit.opacity }} title={`${visit.name} visited this note`} />)}</div>
    <Handle type="source" position={Position.Right} />
  </div>;
}

function CuratorEdge(props: EdgeProps) {
  const { activity, now } = useContext(VisitContext);
  const [path] = getBezierPath(props);
  const visits = activeVisits(activity, 'edges', props.id, now);
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
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<NoteData>>([]);
  useEffect(() => {
    const search = query.trim().toLowerCase();
    setNodes((current) => {
      const previous = new Map(current.map((node) => [node.id, node]));
      return graph.nodes.flatMap((note, index) => {
        if ((noteType !== 'all' && note.type !== noteType)
          || (search && !`${note.id} ${note.title} ${note.type} ${note.path}`.toLowerCase().includes(search))) return [];
        return [{ ...previous.get(note.id), id: note.id, type: 'note',
          position: { x: (index % 3) * 285, y: Math.floor(index / 3) * 155 },
          data: { note }, selected: selectedId === note.id,
          ariaLabel: `${note.title}, ${note.type} note`, style: { width: 220 } }];
      });
    });
  }, [graph, query, noteType, selectedId, setNodes]);
  const visibleIds = new Set(nodes.map(({ id }) => id));
  const edges: Edge[] = graph.edges.filter(({ source, target }) => visibleIds.has(source) && visibleIds.has(target))
    .map((edge) => ({ ...edge, type: 'curator',
      markerEnd: { type: MarkerType.ArrowClosed, color: '#82708f' }, style: { stroke: '#82708f', strokeWidth: 1.5 } }));
  return <VisitContext.Provider value={{ activity, now }}><section className="graph-panel panel" aria-label="Interactive knowledge graph">
    <div className="graph-caption"><span>{nodes.length} notes · {edges.length} links</span><span>Drag to pan · scroll to zoom</span></div>
    <div className="graph-canvas"><ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} nodeTypes={nodeTypes} edgeTypes={edgeTypes}
      fitView fitViewOptions={{ padding: 0.3 }} nodesDraggable={false} nodesConnectable={false} edgesReconnectable={false} deleteKeyCode={null}
      onNodeClick={(_, node) => onSelect(node.id)} minZoom={0.2} maxZoom={2} colorMode="dark">
      <Background color="#59436c" gap={24} /><Controls showInteractive={false} />
    </ReactFlow>{nodes.length === 0 && <p className="graph-empty">{graph.nodes.length === 0 ? 'The knowledge base has no notes yet.' : 'No notes match these filters.'}</p>}</div>
  </section></VisitContext.Provider>;
}
