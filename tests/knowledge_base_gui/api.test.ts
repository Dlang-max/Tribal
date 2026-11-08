// Check API validation at the real HTTP/stream parsing boundary.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchGraph, parseActivityEvent } from '@gui/api';
import { event, graph } from './fixtures';

afterEach(() => vi.unstubAllGlobals());

describe('live graph API boundary', () => {
  it('loads backend note identifiers and rejects HTTP failure instead of making sample data', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json(graph)).mockResolvedValueOnce(new Response('Unavailable', { status: 503 })));
    expect(await fetchGraph()).toEqual(graph);
    await expect(fetchGraph()).rejects.toThrow();
  });

  it.each([
    null,
    { project_id: 'project-live', nodes: [{ id: 'broken' }], edges: [] },
    { ...graph, edges: [{ id: 'bad-link', source: 'note-a' }] },
  ])('rejects malformed graph snapshots: %j', async (snapshot) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(snapshot)));
    await expect(fetchGraph()).rejects.toThrow();
  });

  it('accepts the complete activity envelope while rejecting unknown or malformed visits', () => {
    expect(parseActivityEvent(event())).toEqual(event());
    for (const invalid of [
      null, { ...event(), type: 'invented' }, { ...event(), node_ids: 'note-a' },
      { ...event(), timestamp: 'yesterday' }, { ...event(), status: 'invented' },
    ]) expect(() => parseActivityEvent(invalid)).toThrow();
  });
});
