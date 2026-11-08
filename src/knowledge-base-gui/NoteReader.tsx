// Fetch and show a selected note's complete Markdown source in a closable, read-only reader.
import { useEffect, useRef, useState } from 'react';
import { fetchNote } from './api';
import type { GraphNode, NoteContent } from './types';

export function NoteReader({ note, onClose }: { note: GraphNode; onClose: () => void }) {
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
      <div className="reader-heading"><div><h2 id="reader-title">{note.title}</h2><p>{note.path}</p></div>
        <button ref={closeButton} onClick={onClose}>← Back to graph</button></div>
      {!content && !error && <p className="reader-message" role="status">Loading note contents…</p>}
      {error && <div className="reader-message"><p role="alert">{error}</p><button onClick={() => setAttempt((value) => value + 1)}>Retry note</button></div>}
      {content && <pre className="note-source" tabIndex={0} aria-label="Markdown source">{content.markdown}</pre>}
    </section>
  </div>;
}
