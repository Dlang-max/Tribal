// Render safe Markdown and GFM with hidden YAML frontmatter and navigable known note links.
import { createContext, memo, useContext, type ComponentProps } from 'react';
import Markdown, { type ExtraProps } from 'react-markdown';
import remarkFrontmatter from 'remark-frontmatter';
import remarkGfm from 'remark-gfm';
import { remarkNoteLinks } from './remarkNoteLinks';
import type { GraphNode } from './types';

const NoteNavigation = createContext<{ targets: Map<string, string>; onSelect: (id: string) => void }>({ targets: new Map(), onSelect: () => {} });

function NoteLink({ node: _, href, children, ...props }: ComponentProps<'a'> & ExtraProps) {
  const { targets, onSelect } = useContext(NoteNavigation);
  return <a {...props} href={href} onClick={(event) => {
    const id = href ? targets.get(href) : undefined;
    if (id && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) { event.preventDefault(); onSelect(id); }
  }}>{children}</a>;
}

function MarkdownTable({ node: _, children, ...props }: ComponentProps<'table'> & ExtraProps) {
  return <div className="markdown-table" tabIndex={0} role="region" aria-label="Markdown table"><table {...props}>{children}</table></div>;
}

function CodeBlock({ node: _, ...props }: ComponentProps<'pre'> & ExtraProps) {
  return <pre {...props} tabIndex={0} aria-label="Code block" />;
}

const components = { a: NoteLink, table: MarkdownTable, pre: CodeBlock };

export const MarkdownPreview = memo(function MarkdownPreview({ markdown, notes, onSelect }: { markdown: string; notes: GraphNode[]; onSelect: (id: string) => void }) {
  const targets = new Map(notes.map((note) => [`#note/${encodeURIComponent(note.id)}`, note.id]));
  return <NoteNavigation.Provider value={{ targets, onSelect }}><div className="note-preview" tabIndex={0} aria-label="Markdown preview"><article className="markdown-body">
    <Markdown skipHtml remarkPlugins={[remarkFrontmatter, remarkGfm, [remarkNoteLinks, { notes }]]} components={components}>{markdown}</Markdown>
  </article></div></NoteNavigation.Provider>;
});
