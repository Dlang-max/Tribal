// Resolve wikilinks in Markdown text nodes without changing inline code, fenced code or links.
import type { GraphNode } from './types';

type MarkdownNode = { type: string; value?: string; url?: string; children?: MarkdownNode[] };

export function remarkNoteLinks({ notes }: { notes: GraphNode[] }) {
  const byPath = new Map(notes.map((note) => [note.path.replace(/\.md$/i, ''), note]));
  return (tree: MarkdownNode) => {
    const transform = (node: MarkdownNode) => {
      if (['link', 'linkReference', 'image', 'imageReference', 'code', 'inlineCode', 'html', 'yaml'].includes(node.type)) return;
      node.children = node.children?.flatMap((child): MarkdownNode[] => {
        if (child.type !== 'text' || !child.value) { transform(child); return [child]; }
        const parts: MarkdownNode[] = [];
        let cursor = 0;
        for (const match of child.value.matchAll(/(?<!!)\[\[([^\]\n]+)\]\]/g)) {
          const [target, alias] = match[1].split('|', 2);
          const path = target.split('#', 1)[0].trim().replace(/^\.\//, '').replace(/\.md$/i, '');
          const note = byPath.get(path);
          if (!note) continue;
          const index = match.index;
          if (index > cursor) parts.push({ type: 'text', value: child.value.slice(cursor, index) });
          parts.push({ type: 'link', url: `#note/${encodeURIComponent(note.id)}`,
            children: [{ type: 'text', value: alias?.trim() || note.title }] });
          cursor = index + match[0].length;
        }
        if (!cursor) return [child];
        if (cursor < child.value.length) parts.push({ type: 'text', value: child.value.slice(cursor) });
        return parts;
      });
    };
    transform(tree);
  };
}
