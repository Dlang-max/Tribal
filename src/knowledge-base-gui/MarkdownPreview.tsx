// Render safe Markdown and GFM with hidden YAML frontmatter and navigable known note links.
import { memo } from 'react';
import Markdown from 'react-markdown';
import remarkFrontmatter from 'remark-frontmatter';
import remarkGfm from 'remark-gfm';
import { remarkNoteLinks } from './remarkNoteLinks';
import type { GraphNode } from './types';

export const MarkdownPreview = memo(function MarkdownPreview({ markdown, notes, onSelect }: { markdown: string; notes: GraphNode[]; onSelect: (id: string) => void }) {
  const targets = new Map(notes.map((note) => [`#note/${encodeURIComponent(note.id)}`, note.id]));
  return <div className="note-preview" tabIndex={0} aria-label="Markdown preview"><article className="markdown-body">
    <Markdown skipHtml remarkPlugins={[remarkFrontmatter, remarkGfm, [remarkNoteLinks, { notes }]]} components={{
      a: ({ node: _, href, children, ...props }) => <a {...props} href={href} onClick={(event) => {
        const id = href ? targets.get(href) : undefined;
        if (id && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) { event.preventDefault(); onSelect(id); }
      }}>{children}</a>,
      table: ({ node: _, children, ...props }) => <div className="markdown-table" tabIndex={0} role="region" aria-label="Markdown table"><table {...props}>{children}</table></div>,
      pre: ({ node: _, ...props }) => <pre {...props} tabIndex={0} aria-label="Code block" />,
    }}>{markdown}</Markdown>
  </article></div>;
});
