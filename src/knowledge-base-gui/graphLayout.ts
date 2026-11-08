// Place note dots with a deterministic, bounded force layout using actual graph links.
import type { GraphSnapshot } from './types';

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
