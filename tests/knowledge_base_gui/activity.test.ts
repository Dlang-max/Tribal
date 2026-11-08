// Verify independent server-timestamp trails, real edge visits, and terminal statuses.
import { describe, expect, it } from 'vitest';
import { activeVisits, applyActivityEvent, emptyActivityState, pruneActivity } from '@gui/activity';
import { event, START } from './fixtures';

describe('concurrent curator trails', () => {
  it('preserves two run colors on shared nodes and edges with independent fades', () => {
    let state = applyActivityEvent(emptyActivityState(), event({ edge_ids: ['link-ab'] }));
    state = applyActivityEvent(state, event({
      run_id: 'run-lin', name: 'Lin curator', color: '#39c8ab',
      timestamp: new Date(START + 4000).toISOString(), edge_ids: ['link-ab'],
    }));
    expect(activeVisits(state, 'nodes', 'note-a', START + 5000)).toEqual(expect.arrayContaining([
      expect.objectContaining({ run_id: 'run-ada', color: '#a67aff', opacity: 0.5 }),
      expect.objectContaining({ run_id: 'run-lin', color: '#39c8ab', opacity: 0.9 }),
    ]));
    expect(activeVisits(state, 'edges', 'link-ab', START + 10000)).toEqual([
      expect.objectContaining({ run_id: 'run-lin', opacity: 0.4 }),
    ]);
    expect(activeVisits(state, 'nodes', 'note-a', START + 14000)).toEqual([]);
  });

  it('revisits reset only the same run and target while unrelated visits expire', () => {
    let state = applyActivityEvent(emptyActivityState(), event({ node_ids: ['note-a', 'note-b'], edge_ids: ['link-ab'] }));
    state = applyActivityEvent(state, event({ run_id: 'run-lin', name: 'Lin curator', color: '#39c8ab' }));
    state = applyActivityEvent(state, event({ timestamp: new Date(START + 8000).toISOString() }));
    state = pruneActivity(state, START + 11000);
    expect(activeVisits(state, 'nodes', 'note-a', START + 11000)).toEqual([
      expect.objectContaining({ run_id: 'run-ada', opacity: 0.7 }),
    ]);
    expect(activeVisits(state, 'nodes', 'note-b', START + 11000)).toEqual([]);
    expect(activeVisits(state, 'edges', 'link-ab', START + 11000)).toEqual([]);
  });

  it('does not turn adjacent search results into traversed edges', () => {
    const state = applyActivityEvent(emptyActivityState(), event({ node_ids: ['note-a', 'note-b'] }));
    expect(activeVisits(state, 'nodes', 'note-a', START)).toHaveLength(1);
    expect(activeVisits(state, 'nodes', 'note-b', START)).toHaveLength(1);
    expect(activeVisits(state, 'edges', 'link-ab', START)).toEqual([]);
  });

  it('keeps trails fading after completion or failure instead of clearing them', () => {
    let state = applyActivityEvent(emptyActivityState(), event());
    state = applyActivityEvent(state, event({ run_id: 'run-lin', name: 'Lin curator', color: '#39c8ab' }));
    state = applyActivityEvent(state, event({ type: 'run_finished', status: 'done', message: 'Context ready', node_ids: [], timestamp: new Date(START + 1000).toISOString() }));
    state = applyActivityEvent(state, event({ type: 'run_failed', status: 'failed', run_id: 'run-lin', name: 'Lin curator', color: '#39c8ab', message: 'Curator exited', node_ids: [], timestamp: new Date(START + 1000).toISOString() }));
    expect(state.runs['run-ada'].status).toBe('done');
    expect(state.runs['run-lin'].status).toBe('failed');
    expect(activeVisits(state, 'nodes', 'note-a', START + 2000)).toHaveLength(2);
    expect(activeVisits(state, 'nodes', 'note-a', START + 10000)).toEqual([]);
  });

  it('ages delayed events from server time and bounds future visit opacity', () => {
    const state = applyActivityEvent(emptyActivityState(), event());
    expect(activeVisits(state, 'nodes', 'note-a', START + 9000)[0].opacity).toBeCloseTo(0.1);
    expect(activeVisits(state, 'nodes', 'note-a', START + 10000)).toEqual([]);
    expect(activeVisits(state, 'nodes', 'note-a', START - 1000)[0].opacity).toBe(1);
  });
});
