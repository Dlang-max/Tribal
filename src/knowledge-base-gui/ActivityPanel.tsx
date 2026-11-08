// Present each server-side curator's current observed action and lifecycle status.
import type { ActivityState } from './types';

export function ActivityPanel({ activity }: { activity: ActivityState }) {
  const runs = Object.values(activity.runs).sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp));
  const working = runs.filter(({ status }) => status === 'working').length;
  return <section className="activity-panel panel" aria-label="Curator activity">
    <div className="section-heading"><h2>Curator activity</h2><span className="count">{working} working</span></div>
    {runs.length === 0 ? <p className="empty">No curator activity observed yet. New runs will appear here.</p>
      : <ul className="run-list">{runs.map((run) => <li key={run.run_id} data-testid="curator-run" data-run-id={run.run_id} data-status={run.status} data-color={run.color}>
        <div className="run-heading"><span className="run-color" style={{ backgroundColor: run.color }} aria-hidden="true" /><strong style={{ color: run.color }}>{run.name}</strong><span className={`run-status status-${run.status}`}>{run.status}</span></div>
        <p>{run.message}</p>
      </li>)}</ul>}
  </section>;
}
