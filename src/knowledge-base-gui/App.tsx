// Compose the full-height note graph, live curator activity and on-demand Markdown reader.
import { useEffect, useState } from 'react';
import { ActivityPanel } from './ActivityPanel';
import { KnowledgeGraph } from './KnowledgeGraph';
import { NoteReader } from './NoteReader';
import { useKnowledgeBase } from './useKnowledgeBase';
import './styles.css';

export function App() {
  const { graph, graphError, loading, streamStatus, streamError, historyGap, activity, now, refresh, reconnect } = useKnowledgeBase();
  const [selectedId, setSelectedId] = useState<string>();
  const [focusedRunId, setFocusedRunId] = useState<string>();
  const [highlightedNodeId, setHighlightedNodeId] = useState<string>();
  useEffect(() => {
    if (focusedRunId && !Object.hasOwn(activity.runs, focusedRunId)) setFocusedRunId(undefined);
  }, [activity.runs, focusedRunId]);
  useEffect(() => {
    if (highlightedNodeId && graph && !graph.nodes.some((note) => note.id === highlightedNodeId)) setHighlightedNodeId(undefined);
  }, [graph, highlightedNodeId]);
  const selected = graph?.nodes.find(({ id }) => id === selectedId);
  const streamLabel = { connecting: 'Connecting to activity', connected: 'Live activity connected', reconnecting: 'Activity reconnecting', error: 'Activity disconnected' }[streamStatus];
  const closeNote = () => {
    setSelectedId(undefined);
    requestAnimationFrame(() => Array.from(document.querySelectorAll<HTMLElement>('.react-flow__node'))
      .find((node) => node.dataset.id === selectedId)?.focus());
  };

  return <main className="knowledge-explorer" aria-label="Tribal knowledge graph">
    <div className="graph-workspace">
      <div className="graph-view" aria-hidden={selected ? true : undefined} inert={Boolean(selected)}>
        {graph ? <KnowledgeGraph graph={graph} activity={activity} now={now} onSelect={setSelectedId} selectedId={selectedId} focusedRunId={focusedRunId} highlightedNodeId={highlightedNodeId} />
          : <section className="graph-placeholder" aria-label="Interactive knowledge graph"><p className="empty">{loading ? 'Loading the project graph…' : 'The graph is unavailable. Refresh to try again.'}</p></section>}
        <div className="connection-tools"><p role="status" className={`connection status-${streamStatus}`}><span aria-hidden="true" />{streamLabel}</p>
          <button type="button" onClick={refresh} disabled={loading}>{loading && graph ? 'Refreshing…' : 'Refresh graph'}</button></div>
        {(graphError || streamError) && <div className="graph-status">
          {graphError && <p role="alert" className="notice error">{graphError} {graph ? 'Showing the last loaded snapshot.' : 'Check the local server and refresh the graph.'}</p>}
          {streamError && <div className="notice" role="status"><span>{streamError}</span>{streamStatus === 'error' && <button onClick={reconnect}>Reconnect activity</button>}</div>}
        </div>}
      </div>
      {selected && <NoteReader key={selected.id} note={selected} notes={graph?.nodes ?? []} onSelect={setSelectedId} onClose={closeNote} />}
    </div>
    <ActivityPanel activity={activity} notes={graph?.nodes ?? []} focusedRunId={focusedRunId} onFocus={setFocusedRunId} onOpen={(id) => {
      setHighlightedNodeId(id);
      setSelectedId(id);
    }} historyGap={historyGap} />
  </main>;
}

export default App;
