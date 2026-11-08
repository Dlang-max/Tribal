// Fetch a note and switch between its rendered Markdown preview and complete read-only source.
import { useEffect, useRef, useState } from 'react';
import { fetchNote } from './api';
import { MarkdownPreview } from './MarkdownPreview';
import type { GraphNode, NoteContent } from './types';

export function NoteReader({ note, notes, onSelect, onClose }: { note: GraphNode; notes: GraphNode[]; onSelect: (id: string) => void; onClose: () => void }) {
  const [view, setView] = useState<'preview' | 'source'>('preview');
  const [content, setContent] = useState<NoteContent>();
  const [error, setError] = useState<string>();
  const [attempt, setAttempt] = useState(0);
  const closeButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeButton.current?.focus();
    const controller = new AbortController();
    let active = true;
    setContent(undefined);
    setError(undefined);
    void fetchNote(note.id, controller.signal).then((value) => {
      if (active) setContent(value);
    }).catch((reason: unknown) => {
      if (active && !controller.signal.aborted) setError(reason instanceof Error ? reason.message : 'Unable to read this note.');
    });
    return () => { active = false; controller.abort(); };
  }, [note.id, attempt]);

  return <div className="reader-overlay">
    <section className="note-reader" role="region" aria-label="Note contents"
      onKeyDown={(event) => {
        if (event.key === 'Escape') { event.stopPropagation(); onClose(); }
      }}>
      <div className="reader-heading"><div><div className="reader-title-row"><h2 id="reader-title">{note.title}</h2>
        {content?.status === 'archived' && <span className="note-status-badge">Archived</span>}</div><p>{note.path}</p></div>
        <button ref={closeButton} onClick={onClose}>← Back to graph</button></div>
      {!content && !error && <p className="reader-message" role="status">Loading note contents…</p>}
      {error && <div className="reader-message"><p role="alert">{error}</p><button onClick={() => setAttempt((value) => value + 1)}>Retry note</button></div>}
      {content && <>
        <div className="reader-view-controls" role="group" aria-label="Note view">
          <button aria-pressed={view === 'preview'} onClick={() => setView('preview')}>Preview</button>
          <button aria-pressed={view === 'source'} onClick={() => setView('source')}>Source</button>
        </div>
        {view === 'preview' ? <MarkdownPreview markdown={content.markdown} notes={notes} onSelect={onSelect} />
          : <pre className="note-source" tabIndex={0} aria-label="Markdown source">{content.markdown}</pre>}
      </>}
    </section>
  </div>;
}
