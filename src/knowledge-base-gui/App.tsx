// Compose the live Markdown graph, accessible note browser, inspector and curator activity.
import { useState } from 'react';
import { ActivityPanel } from './ActivityPanel';
import { KnowledgeGraph } from './KnowledgeGraph';
import { useKnowledgeBase } from './useKnowledgeBase';
import './styles.css';

export function App() {
  const { graph, graphError, loading, streamStatus, streamError, activity, now, refresh, reconnect } = useKnowledgeBase();
  const [query, setQuery] = useState('');
  const [noteType, setNoteType] = useState('all');
  const [selectedId, setSelectedId] = useState<string>();
  const selected = graph?.nodes.find(({ id }) => id === selectedId);
  const visible = graph?.nodes.filter((note) => (noteType === 'all' || note.type === noteType)
    && `${note.id} ${note.title} ${note.type} ${note.path}`.toLowerCase().includes(query.trim().toLowerCase())) ?? [];
  const links = graph?.edges.filter(({ source, target }) => source === selectedId || target === selectedId) ?? [];
  const streamLabel = { connecting: 'Connecting to activity', connected: 'Live activity connected', reconnecting: 'Activity reconnecting', error: 'Activity disconnected' }[streamStatus];

  return <main className="knowledge-explorer">
    <header className="page-heading"><div><p className="eyebrow">TRIBAL / SHARED CONTEXT</p><h1>Knowledge explorer</h1>
      <p className="muted">{graph ? graph.project_id : 'Project knowledge base'} · Markdown notes, connected.</p></div>
      <div className="connection-tools"><p role="status" className={`connection status-${streamStatus}`}><span aria-hidden="true" />{streamLabel}</p>
        <button type="button" onClick={refresh} disabled={loading}>{loading && graph ? 'Refreshing…' : 'Refresh graph'}</button></div>
    </header>
    {graphError && <p role="alert" className="notice error">{graphError} {graph ? 'Showing the last loaded snapshot.' : 'Check the local server and refresh the graph.'}</p>}
    {streamError && <div className="notice" role="status"><span>{streamError}</span>{streamStatus === 'error' && <button onClick={reconnect}>Reconnect activity</button>}</div>}
    <div className="workspace">
      <aside className="browse-panel panel" aria-label="Note browser"><div className="section-heading"><h2>Notes</h2><span className="count">{graph?.nodes.length ?? 0}</span></div>
        <label className="field">Search notes<input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Title, type or path…" /></label>
        <label className="field">Note type<select value={noteType} onChange={(event) => setNoteType(event.target.value)}><option value="all">All note types</option>{Array.from(new Set(graph?.nodes.map(({ type }) => type))).sort().map((type) => <option key={type} value={type}>{type}</option>)}</select></label>
        {loading && !graph && <p role="status" className="empty">Loading knowledge graph…</p>}
        {graph && visible.length === 0 && <p className="empty">{graph.nodes.length === 0 ? 'No notes yet. Curated notes will appear here.' : 'No notes match these filters.'}</p>}
        <ul className="note-list">{visible.map((note) => <li key={note.id}><button onClick={() => setSelectedId(note.id)} aria-pressed={selectedId === note.id}><small>{note.type}</small><strong>{note.title}</strong><span>{note.path}</span></button></li>)}</ul>
      </aside>
      <div className="graph-column">{graph ? <KnowledgeGraph graph={graph} activity={activity} now={now} onSelect={setSelectedId} selectedId={selectedId} query={query} noteType={noteType} />
        : <section className="graph-placeholder panel" aria-label="Interactive knowledge graph"><p className="empty">{loading ? 'Loading the project graph…' : 'The graph is unavailable. Refresh to try again.'}</p></section>}
        <section className="inspector panel" aria-label="Note details"><p className="eyebrow">NOTE DETAILS</p>{selected ? <><h2>{selected.title}</h2><dl className="note-fields"><div><dt>Type</dt><dd>{selected.type}</dd></div><div><dt>Path</dt><dd>{selected.path}</dd></div><div><dt>Note ID</dt><dd>{selected.id}</dd></div></dl>
          <h3>Linked notes</h3>{links.length === 0 ? <p className="muted">This note has no links.</p> : <ul className="neighbor-list">{links.map((edge) => {
            const outgoing = edge.source === selectedId;
            const neighbor = graph?.nodes.find(({ id }) => id === (outgoing ? edge.target : edge.source));
            return neighbor ? <li key={edge.id}><button onClick={() => setSelectedId(neighbor.id)}><span>{outgoing ? 'To' : 'From'} · {neighbor.title}</span><small>{neighbor.type}</small></button></li> : null;
          })}</ul>}</> : <><h2>Select a note</h2><p className="muted">Choose a note in the graph or browser to inspect its metadata and linked notes.</p></>}</section>
      </div>
      <ActivityPanel activity={activity} />
    </div>
  </main>;
}

export default App;
