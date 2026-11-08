// Show observed run focus, latest reads and receipt-backed publication outcomes.
import type { ActivityState, GraphNode, PublicationNote, RunActivity } from './types';

type PanelProps = {
  activity: ActivityState;
  notes: GraphNode[];
  focusedRunId?: string;
  onFocus: (id?: string) => void;
  onOpen: (id: string) => void;
  historyGap: boolean;
};

function NoteReference({ note, label, onOpen }: {
  note?: GraphNode; label: string; onOpen: PanelProps['onOpen'];
}) {
  return note ? <span className="note-reference">
    <button type="button" className="note-reference-name" aria-label={`Open ${note.title}`} onClick={() => onOpen(note.id)}>{note.title}</button>
  </span> : <span className="unavailable-note">{label} <span className="muted">(unavailable)</span></span>;
}

function PublicationSummary({ run, notes, onOpen }: {
  run: RunActivity; notes: GraphNode[]; onOpen: PanelProps['onOpen'];
}) {
  const publication = run.publicationEvent?.publication;
  if (!publication) return null;
  const receipts = run.receipts ?? [];
  const count = (action: PublicationNote['action']) => receipts.filter((note) => note.action === action).length;
  return <div className="publication-summary">
    <p><strong>{receipts.length > 0 ? '✓ Publication confirmed' : publication.status === 'unchanged' ? 'No changes published' : publication.status === 'needs_information' ? 'More information needed' : 'Publication reported without note receipts'}</strong></p>
    {receipts.length > 0 && publication.status !== 'updated' && <p className="muted">Latest outcome: {publication.status === 'unchanged' ? 'unchanged' : 'more information needed'}. Confirmed saves are retained.</p>}
    {receipts.length > 0 && <><p className="muted">Confirmed receipts: {count('created')} created · {count('updated')} updated · {count('archived')} archived</p>
      <ul className="receipt-list">{receipts.map((receipt) => {
        const note = notes.find((note) => note.id === receipt.note_id || note.path === receipt.path);
        return <li key={`${receipt.action}:${receipt.path}`}><small>{receipt.action}</small>
          <NoteReference note={note} label={receipt.path} onOpen={onOpen} />
        </li>;
      })}</ul></>}
    {run.status === 'failed' && receipts.length > 0 && <p className="muted">These changes were saved before the run failed.</p>}
  </div>;
}

export function ActivityPanel({ activity, notes, focusedRunId, onFocus, onOpen, historyGap }: PanelProps) {
  const runs = Object.values(activity.runs).sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp));
  const working = runs.filter(({ status }) => status === 'working').length;
  return <section className="activity-panel panel" aria-label="Curator activity">
    <div className="section-heading"><h2>Curator activity</h2><span className="count">{working} working</span></div>
    {historyGap && <p className="history-gap" role="status">History gap: activity may be missing after a disconnect or unreadable event. Reconnecting does not replay missed actions.</p>}
    {focusedRunId && <button type="button" className="reset-focus" onClick={() => onFocus(undefined)}>Show all runs</button>}
    {runs.length === 0 ? <p className="empty">No curator activity observed yet. New runs will appear here.</p>
      : <ul className="run-list">{runs.map((run) => {
        return <li key={run.run_id} data-testid="curator-run" data-run-id={run.run_id} data-status={run.status} data-color={run.color}
          className={focusedRunId && focusedRunId !== run.run_id ? 'run-dimmed' : undefined}>
          <div className="run-heading"><span className="run-color" style={{ backgroundColor: run.color }} aria-hidden="true" /><strong style={{ color: run.color }}>{run.name}</strong><span className={`run-status status-${run.status}`}>{run.status}</span></div>
          <p>{run.message}</p>
          {(run.action || run.run_kind) && <p className="muted">{[run.run_kind, run.action].filter(Boolean).join(' · ')}</p>}
          {run.lastRead && <div className="last-read"><small>Last observed read</small><NoteReference note={notes.find((note) => note.id === run.lastRead?.target_node_id)} label={run.lastRead.target_node_id ?? ''} onOpen={onOpen} /></div>}
          <PublicationSummary run={run} notes={notes} onOpen={onOpen} />
          <div className="run-controls"><button type="button" aria-pressed={focusedRunId === run.run_id} aria-label={`Focus ${run.name}`} onClick={() => onFocus(focusedRunId === run.run_id ? undefined : run.run_id)}>Focus run</button></div>
        </li>;
      })}</ul>}
  </section>;
}
