// Place note dots and separate overlapping label areas without changing the graph's links.
import type { GraphSnapshot } from './types';

export const LABEL_WIDTH = 176;
export const LABEL_HEIGHT = 40;
export const LABEL_MIN_ZOOM = 0.65;

type PositionedNote = { id: string; position: { x: number; y: number } };

// Resolve nearby dot/label collisions while keeping the user's active note stationary.
export function spaceGraphNodes<T extends PositionedNote>(nodes: T[], zoom: number, pinnedId?: string, animate = true): T[] {
  const labelsVisible = zoom >= LABEL_MIN_ZOOM;
  const width = labelsVisible ? Math.max(44, (LABEL_WIDTH + 12) / zoom) : 44;
  const height = labelsVisible ? 34 + (LABEL_HEIGHT + 12) / zoom : 44;
  const offsets = nodes.map(() => ({ x: 0, y: 0 }));
  const cells = new Map<string, number[]>();
  let overlapping = false;
  nodes.forEach((node, index) => {
    const cellX = Math.floor(node.position.x / width);
    const cellY = Math.floor(node.position.y / height);
    for (let x = cellX - 1; x <= cellX + 1; x++) {
      for (let y = cellY - 1; y <= cellY + 1; y++) {
        for (const other of cells.get(`${x},${y}`) ?? []) {
          const dx = node.position.x - nodes[other].position.x;
          const dy = node.position.y - nodes[other].position.y;
          const overlapX = width - Math.abs(dx);
          const overlapY = height - Math.abs(dy);
          if (overlapX <= 0.1 || overlapY <= 0.1) continue;
          const pinned = node.id === pinnedId;
          const otherPinned = nodes[other].id === pinnedId;
          const share = pinned || otherPinned ? 1 : 0.5;
          const axis = overlapX < overlapY ? 'x' : 'y';
          const distance = axis === 'x' ? dx : dy;
          const shift = (axis === 'x' ? overlapX : overlapY) * (distance < 0 ? -1 : 1) * share;
          if (!pinned) offsets[index][axis] += shift;
          if (!otherPinned) offsets[other][axis] -= shift;
          overlapping = true;
        }
      }
    }
    const key = `${cellX},${cellY}`;
    const cell = cells.get(key) ?? [];
    cell.push(index);
    cells.set(key, cell);
  });
  if (!overlapping) return nodes;
  const limit = animate ? 6 / zoom : Infinity;
  return nodes.map((node, index) => {
    const offset = offsets[index];
    if (!offset.x && !offset.y) return node;
    return { ...node, position: {
      x: node.position.x + Math.max(-limit, Math.min(limit, offset.x * 0.6)),
      y: node.position.y + Math.max(-limit, Math.min(limit, offset.y * 0.6)),
    } };
  });
}

export function layoutGraph(graph: GraphSnapshot): Map<string, { x: number; y: number }> {
  const notes = [...graph.nodes].sort((a, b) => a.id.localeCompare(b.id));
  const radius = Math.max(120, Math.sqrt(notes.length) * 70);
  const points = notes.map((note, index) => {
    const angle = index * 2.399963;
    const distance = radius * Math.sqrt((index + 1) / Math.max(1, notes.length));
    return { id: note.id, x: Math.cos(angle) * distance, y: Math.sin(angle) * distance };
  });
  const indices = new Map(points.map((point, index) => [point.id, index]));
  // Sample repulsion for larger vaults to keep layout work bounded without a new dependency.
  const stride = Math.max(1, Math.ceil(points.length / 160));
  for (let step = 0; step < 120; step++) {
    const forces = points.map((point) => ({ x: -point.x * 0.004, y: -point.y * 0.004 }));
    points.forEach((point, index) => {
      for (let other = (step % stride); other < points.length; other += stride) {
        if (other === index) continue;
        const dx = point.x - points[other].x;
        const dy = point.y - points[other].y;
        const distance = Math.max(24, Math.hypot(dx, dy));
        const force = 2400 / (distance * distance);
        forces[index].x += dx / distance * force;
        forces[index].y += dy / distance * force;
      }
    });
    for (const edge of graph.edges) {
      const source = indices.get(edge.source);
      const target = indices.get(edge.target);
      if (source === undefined || target === undefined || source === target) continue;
      const dx = points[target].x - points[source].x;
      const dy = points[target].y - points[source].y;
      const distance = Math.max(1, Math.hypot(dx, dy));
      const force = (distance - 175) * 0.025;
      forces[source].x += dx / distance * force;
      forces[source].y += dy / distance * force;
      forces[target].x -= dx / distance * force;
      forces[target].y -= dy / distance * force;
    }
    const cooling = 1 - step / 160;
    points.forEach((point, index) => {
      point.x += Math.max(-10, Math.min(10, forces[index].x)) * cooling;
      point.y += Math.max(-10, Math.min(10, forces[index].y)) * cooling;
    });
  }
  return new Map(points.map(({ id, x, y }) => [id, { x, y }]));
}
