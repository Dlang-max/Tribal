// Render note dots, straight links and independently fading curator trails with React Flow.
import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { BaseEdge, Controls, Handle, Position, ReactFlow, useNodesState,
  type Edge, type EdgeProps, type Node, type NodeProps } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { activeVisits, emptyActivityState } from './activity';
import { layoutGraph } from './graphLayout';
import type { ActivityState, GraphNode, GraphSnapshot } from './types';

type NoteData = { note: GraphNode; connections: number };
const VisitContext = createContext({ activity: emptyActivityState(), now: 0 });

function NoteNode({ id, data }: NodeProps<Node<NoteData>>) {
  const { activity, now } = useContext(VisitContext);
  const visits = activeVisits(activity, 'nodes', id, now);
  const radius = Math.min(14, 5 + 2 * Math.sqrt(data.connections));
  return <div className="note-node" title={`${data.note.title} · ${data.connections} connected notes`}>
    <Handle type="target" position={Position.Left} />
    <svg className="node-rings" viewBox="-22 -22 44 44" aria-hidden="true" overflow="visible">
      {visits.map((visit, index) => <circle key={visit.run_id} cx="0" cy="0" r={radius + 4 + index * 4} fill="none" stroke={visit.color} strokeWidth="2"
        data-testid="node-visit" data-target-id={id} data-run-id={visit.run_id} data-color={visit.color} data-opacity={visit.opacity}
        style={{ opacity: visit.opacity }}><title>{visit.name} visited this note</title></circle>)}
      <circle className="note-dot" cx="0" cy="0" r={radius} />
    </svg>
    <span className="note-label">{data.note.title}</span>
    <Handle type="source" position={Position.Right} />
  </div>;
}

function CuratorEdge(props: EdgeProps) {
  const { activity, now } = useContext(VisitContext);
  const visits = activeVisits(activity, 'edges', props.id, now);
  const path = `M ${props.sourceX},${props.sourceY} L ${props.targetX},${props.targetY}`;
  const length = Math.hypot(props.targetX - props.sourceX, props.targetY - props.sourceY) || 1;
  return <g>
    <BaseEdge id={props.id} path={path} style={props.style} interactionWidth={16} />
    {visits.map((visit, index) => {
      const offset = (index - (visits.length - 1) / 2) * 4;
      const dx = -(props.targetY - props.sourceY) / length * offset;
      const dy = (props.targetX - props.sourceX) / length * offset;
      return <path key={visit.run_id} d={`M ${props.sourceX + dx},${props.sourceY + dy} L ${props.targetX + dx},${props.targetY + dy}`} fill="none" stroke={visit.color} strokeWidth={1.6}
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
}

export function KnowledgeGraph({ graph, activity, now, onSelect, selectedId }: KnowledgeGraphProps) {
  const [hoveredId, setHoveredId] = useState<string>();
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<NoteData>>([]);
  const positions = useMemo(() => layoutGraph(graph), [graph]);
  const connections = useMemo(() => {
    const neighbors = new Map(graph.nodes.map((note) => [note.id, new Set<string>()]));
    for (const edge of graph.edges) {
      if (edge.source === edge.target || !neighbors.has(edge.source) || !neighbors.has(edge.target)) continue;
      neighbors.get(edge.source)!.add(edge.target);
      neighbors.get(edge.target)!.add(edge.source);
    }
    return new Map([...neighbors].map(([id, linked]) => [id, linked.size]));
  }, [graph]);
  useEffect(() => {
    setNodes((current) => {
      const previous = new Map(current.map((node) => [node.id, node]));
      return graph.nodes.map((note) => ({ ...previous.get(note.id), id: note.id, type: 'note',
        position: positions.get(note.id) ?? { x: 0, y: 0 }, data: { note, connections: connections.get(note.id) ?? 0 }, selected: selectedId === note.id,
        ariaRole: 'button', ariaLabel: `${note.title}, ${note.type} note. ${connections.get(note.id) ?? 0} connected notes. Open note`, style: { width: 44, height: 44 } }));
    });
  }, [graph, positions, connections, selectedId, setNodes]);
  const edges: Edge[] = graph.edges.map((edge) => ({ ...edge, type: 'curator', style: { stroke: edge.source === hoveredId ? '#b49ae8' : '#62616a', strokeWidth: edge.source === hoveredId ? 3.4 : 1 } }));
  return <VisitContext.Provider value={{ activity, now }}><section className="graph-panel" aria-label="Interactive knowledge graph"
    onKeyDownCapture={(event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      const node = (event.target as HTMLElement).closest<HTMLElement>('.react-flow__node');
      if (node?.dataset.id) { event.preventDefault(); event.stopPropagation(); onSelect(node.dataset.id); }
    }}>
    <div className="graph-caption"><span>{graph.nodes.length} notes · {edges.length} links</span><span>Click a note to read</span></div>
    <div className="graph-canvas"><ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} nodeTypes={nodeTypes} edgeTypes={edgeTypes}
      fitView fitViewOptions={{ padding: 0.35, maxZoom: 1.2 }} nodesDraggable={false} nodesConnectable={false} edgesReconnectable={false} deleteKeyCode={null}
      onNodeMouseEnter={(_, node) => setHoveredId(node.id)} onNodeMouseLeave={() => setHoveredId(undefined)}
      onNodeClick={(_, node) => onSelect(node.id)} minZoom={0.15} maxZoom={3} colorMode="dark">
      <Controls showInteractive={false} />
    </ReactFlow>{nodes.length === 0 && <p className="graph-empty">The knowledge base has no notes yet.</p>}</div>
  </section></VisitContext.Provider>;
}
