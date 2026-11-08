// Space readable note dots and layer highlighted links with independently fading curator colors.
import { createContext, useContext, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { BaseEdge, Controls, Handle, Position, ReactFlow, useNodesState,
  type Edge, type EdgeProps, type Node, type NodeProps } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { activeVisits, emptyActivityState } from './activity';
import { LABEL_HEIGHT, LABEL_MIN_ZOOM, LABEL_WIDTH, layoutGraph, spaceGraphNodes } from './graphLayout';
import type { ActivityState, GraphNode, GraphSnapshot } from './types';

type NoteData = { note: GraphNode; connections: number };
const VisitContext = createContext<{ activity: ActivityState; now: number; focusedRunId?: string;
  focusedNodes?: Set<string>; focusedEdges?: Set<string>; highlightedNodeId?: string }>({ activity: emptyActivityState(), now: 0 });
const LabelContext = createContext(new Set<string>());

// Reserve screen space for dots and labels, favoring the active and most connected notes.
function readableLabels(nodes: Node<NoteData>[], zoom: number, activeId?: string): Set<string> {
  const visible = new Set<string>();
  if (zoom < LABEL_MIN_ZOOM && !activeId) return visible;
  const dots = nodes.map((node) => ({ id: node.id,
    x: (node.position.x + 22) * zoom, y: (node.position.y + 22) * zoom,
    radius: Math.min(14, 5 + 2 * Math.sqrt(node.data.connections)) * zoom + 4 }));
  const occupied: { left: number; right: number; top: number; bottom: number }[] = [];
  const candidates = [...nodes].sort((a, b) =>
    Number(b.id === activeId) - Number(a.id === activeId)
    || Number(!!b.selected) - Number(!!a.selected)
    || b.data.connections - a.data.connections || a.id.localeCompare(b.id));
  for (const node of candidates) {
    const active = node.id === activeId;
    if (zoom < LABEL_MIN_ZOOM && !active) continue;
    const center = (node.position.x + 22) * zoom;
    const top = (node.position.y + 42) * zoom;
    const box = { left: center - LABEL_WIDTH / 2, right: center + LABEL_WIDTH / 2,
      top, bottom: top + LABEL_HEIGHT };
    const labelOverlap = occupied.some((other) => box.left < other.right + 6
      && box.right + 6 > other.left && box.top < other.bottom + 6 && box.bottom + 6 > other.top);
    const dotOverlap = dots.some((dot) => dot.id !== node.id && box.left < dot.x + dot.radius
      && box.right > dot.x - dot.radius && box.top < dot.y + dot.radius && box.bottom > dot.y - dot.radius);
    if (!active && (labelOverlap || dotOverlap)) continue;
    visible.add(node.id);
    occupied.push(box);
  }
  return visible;
}

function NoteNode({ id, data }: NodeProps<Node<NoteData>>) {
  const { activity, now, focusedRunId, focusedNodes, highlightedNodeId } = useContext(VisitContext);
  const labels = useContext(LabelContext);
  const visits = activeVisits(activity, 'nodes', id, now);
  const radius = Math.min(14, 5 + 2 * Math.sqrt(data.connections));
  const readers = Object.values(activity.runs).filter((run) => run.lastRead?.target_node_id === id
    && (focusedRunId ? run.run_id === focusedRunId : run.status === 'working'));
  const publicationOpacity = Math.max(0, ...visits.filter((visit) => visit.action === 'publish'
    && (!focusedRunId || visit.run_id === focusedRunId)).map((visit) => visit.opacity));
  return <div className="note-node" data-run-dimmed={Boolean(focusedNodes && !focusedNodes.has(id) && highlightedNodeId !== id)} title={`${data.note.title} · ${data.connections} connected notes`}>
    <Handle type="target" position={Position.Left} />
    <svg className="node-shape" viewBox="-22 -22 44 44" aria-hidden="true">
      <circle className="note-dot" cx="0" cy="0" r={radius} />
      {visits.map((visit, index) => {
        const attributes = { fill: visit.action === 'search' ? 'none' : visit.color,
          stroke: visit.action === 'search' ? visit.color : undefined, strokeWidth: visit.action === 'search' ? 2 : undefined,
          style: { opacity: visit.opacity * (focusedRunId && focusedRunId !== visit.run_id ? .2 : 1) },
          'data-testid': 'node-visit', 'data-target-id': id, 'data-run-id': visit.run_id,
          'data-color': visit.color, 'data-opacity': visit.opacity, 'data-action': visit.action };
        if (visits.length === 1) return <circle key={visit.run_id} cx="0" cy="0" r={radius} {...attributes}>
          <title>{visit.name}: {visit.action ?? 'visited'} this note</title>
        </circle>;
        const start = index / visits.length * 2 * Math.PI - Math.PI / 2;
        const end = (index + 1) / visits.length * 2 * Math.PI - Math.PI / 2;
        return <path key={visit.run_id} d={`${visit.action === 'search' ? 'M' : 'M 0,0 L'} ${radius * Math.cos(start)},${radius * Math.sin(start)} A ${radius},${radius} 0 0 1 ${radius * Math.cos(end)},${radius * Math.sin(end)}${visit.action === 'search' ? '' : ' Z'}`} {...attributes}>
          <title>{visit.name}: {visit.action ?? 'visited'} this note</title>
        </path>;
      })}
      <circle className="note-outline" cx="0" cy="0" r={radius} />
      {publicationOpacity > 0 && <path className="publication-check" d="M -5,0 L -1,4 L 6,-4" fill="none" stroke="#fff" strokeWidth="2" opacity={publicationOpacity}><title>Confirmed publication</title></path>}
    </svg>
    <span className="note-label" data-visible={labels.has(id)} aria-hidden="true"><span className="note-label-text">{data.note.title}</span></span>
    {readers.length > 0 && (labels.has(id) || focusedRunId) && <span className="last-read-tag" aria-hidden="true" title={readers.map((run) => run.name).join(', ')}>Read · {readers.slice(0, 2).map((run) => run.name).join(', ')}{readers.length > 2 ? ` +${readers.length - 2}` : ''}</span>}
    <Handle type="source" position={Position.Right} />
  </div>;
}

function CuratorEdge(props: EdgeProps) {
  const { activity, now, focusedRunId, focusedEdges } = useContext(VisitContext);
  const visits = activeVisits(activity, 'edges', props.id, now);
  const path = `M ${props.sourceX},${props.sourceY} L ${props.targetX},${props.targetY}`;
  return <g opacity={focusedEdges && !focusedEdges.has(props.id) ? .18 : 1}>
    <BaseEdge id={props.id} path={path} style={props.style} interactionWidth={16} />
    {visits.map((visit, index) => {
      const start = index / visits.length;
      const end = (index + 1) / visits.length;
      const dx = props.targetX - props.sourceX;
      const dy = props.targetY - props.sourceY;
      const segment = `M ${props.sourceX + dx * start},${props.sourceY + dy * start} L ${props.sourceX + dx * end},${props.sourceY + dy * end}`;
      const opacity = visit.opacity * (focusedRunId && focusedRunId !== visit.run_id ? .2 : 1);
      const directed = visit.action === 'traverse' && visit.target_node_id === props.target;
      return <g key={visit.run_id}>
        <path d={segment} fill="none" stroke={visit.color} strokeWidth={1.6}
        opacity={visit.opacity} style={{ opacity, pointerEvents: 'none' }}
        data-testid="edge-visit" data-target-id={props.id} data-run-id={visit.run_id} data-color={visit.color} data-opacity={visit.opacity} data-action={visit.action}>
        <title>{visit.name} followed this link</title>
        </path>
        {directed && <g className="traversal-direction" style={{ opacity, pointerEvents: 'none' }}>
          <path className="traversal-pulse" d={segment} fill="none" stroke={visit.color} strokeWidth="3" strokeDasharray="2 12" />
          <path d="M -5,-4 L 0,0 L -5,4" fill="none" stroke={visit.color} strokeWidth="2"
            transform={`translate(${props.sourceX + dx * (start + (end - start) * .7)},${props.sourceY + dy * (start + (end - start) * .7)}) rotate(${Math.atan2(dy, dx) * 180 / Math.PI})`}>
            <title>{visit.name}: direction to {props.target}</title>
          </path>
        </g>}
      </g>;
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
  focusedRunId?: string;
  highlightedNodeId?: string;
}

export function KnowledgeGraph({ graph, activity, now, onSelect, selectedId, focusedRunId, highlightedNodeId }: KnowledgeGraphProps) {
  const [hoveredId, setHoveredId] = useState<string>();
  const [focusedId, setFocusedId] = useState<string>();
  const [zoom, setZoom] = useState(1);
  const [dragging, setDragging] = useState(false);
  const [lastDraggedId, setLastDraggedId] = useState<string>();
  const [reducedMotion, setReducedMotion] = useState(false);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<NoteData>>([]);
  const currentNodes = useRef(nodes);
  useEffect(() => { currentNodes.current = nodes; }, [nodes]);
  useEffect(() => {
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReducedMotion(preference.matches);
    update();
    preference.addEventListener('change', update);
    return () => preference.removeEventListener('change', update);
  }, []);
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
        position: previous.get(note.id)?.position ?? positions.get(note.id) ?? { x: 0, y: 0 }, data: { note, connections: connections.get(note.id) ?? 0 }, selected: selectedId === note.id,
        zIndex: 3, ariaRole: 'button', ariaLabel: `${note.title}, ${note.type} note. ${connections.get(note.id) ?? 0} connected notes. Open note`, style: { width: 44, height: 44 } }));
    });
  }, [graph, positions, connections, selectedId, setNodes]);
  useEffect(() => {
    if (dragging || selectedId) return;
    let frame = 0;
    let steps = 0;
    const pinnedId = hoveredId ?? focusedId ?? lastDraggedId;
    const settle = () => {
      let next = currentNodes.current;
      const previous = next;
      // Reduced motion resolves spacing in one paint rather than animating the graph.
      for (let step = 0; step < (reducedMotion ? 120 : 1); step++) {
        const spaced = spaceGraphNodes(next, zoom, pinnedId, !reducedMotion);
        if (spaced === next) break;
        next = spaced;
      }
      if (next === previous) return;
      currentNodes.current = next;
      setNodes(next);
      if (!reducedMotion && ++steps < 120) frame = requestAnimationFrame(settle);
    };
    frame = requestAnimationFrame(settle);
    return () => cancelAnimationFrame(frame);
  }, [graph, zoom, dragging, selectedId, hoveredId, focusedId, lastDraggedId, reducedMotion, setNodes]);
  const labels = useMemo(() => readableLabels(nodes, zoom, hoveredId ?? focusedId ?? highlightedNodeId), [nodes, zoom, hoveredId, focusedId, highlightedNodeId]);
  const focusedTargets = useMemo(() => {
    const run = focusedRunId ? activity.runs[focusedRunId] : undefined;
    if (!run) return undefined;
    const nodes = new Set<string>(run.observed_node_ids);
    const edges = new Set<string>(run.observed_edge_ids);
    for (const event of [run, ...(run.lastRead ? [run.lastRead] : [])]) {
      event.node_ids.forEach((id) => nodes.add(id));
      event.edge_ids.forEach((id) => edges.add(id));
      if (event.target_node_id) nodes.add(event.target_node_id);
    }
    for (const receipt of run.receipts ?? []) {
      const note = graph.nodes.find((note) => note.id === receipt.note_id || note.path === receipt.path);
      if (note) nodes.add(note.id);
    }
    for (const edge of graph.edges) if (edges.has(edge.id)) { nodes.add(edge.source); nodes.add(edge.target); }
    return { nodes, edges };
  }, [activity.runs, focusedRunId, graph]);
  const edges: Edge[] = graph.edges.map((edge) => ({ ...edge, type: 'curator',
    zIndex: activeVisits(activity, 'edges', edge.id, now).length ? 2 : edge.source === hoveredId ? 1 : 0,
    style: { stroke: edge.source === hoveredId ? '#b49ae8' : '#62616a', strokeWidth: edge.source === hoveredId ? 3.4 : 1 } }));
  return <VisitContext.Provider value={{ activity, now, focusedRunId, focusedNodes: focusedTargets?.nodes, focusedEdges: focusedTargets?.edges, highlightedNodeId }}><LabelContext.Provider value={labels}><section className="graph-panel" aria-label="Interactive knowledge graph"
    style={{ '--note-label-scale': 1 / zoom, '--note-label-width': `${LABEL_WIDTH}px`, '--note-label-height': `${LABEL_HEIGHT}px` } as CSSProperties}
    onFocusCapture={(event) => setFocusedId((event.target as HTMLElement).closest<HTMLElement>('.react-flow__node')?.dataset.id)}
    onBlurCapture={() => setFocusedId(undefined)}
    onKeyDownCapture={(event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      const node = (event.target as HTMLElement).closest<HTMLElement>('.react-flow__node');
      if (node?.dataset.id) { event.preventDefault(); event.stopPropagation(); onSelect(node.dataset.id); }
    }}>
    <div className="graph-caption"><span>{graph.nodes.length} notes · {edges.length} links</span></div>
    <div className="graph-canvas"><ReactFlow nodes={nodes} edges={edges} onNodesChange={onNodesChange} nodeTypes={nodeTypes} edgeTypes={edgeTypes}
      fitView fitViewOptions={{ padding: 0.35, maxZoom: 1.2 }} nodesDraggable nodeDragThreshold={4} nodesConnectable={false} edgesReconnectable={false} deleteKeyCode={null}
      onInit={(instance) => setZoom(instance.getZoom())} onMove={(_, viewport) => setZoom(viewport.zoom)}
      onNodeDragStart={(_, node) => { setDragging(true); setLastDraggedId(node.id); }} onNodeDragStop={() => setDragging(false)}
      onNodeMouseEnter={(_, node) => setHoveredId(node.id)} onNodeMouseLeave={() => setHoveredId(undefined)}
      onNodeClick={(_, node) => onSelect(node.id)} minZoom={0.15} maxZoom={3} colorMode="dark">
      <Controls showInteractive={false} />
    </ReactFlow>{nodes.length === 0 && <p className="graph-empty">The knowledge base has no notes yet.</p>}</div>
  </section></LabelContext.Provider></VisitContext.Provider>;
}
