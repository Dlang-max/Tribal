// Check API validation at the real HTTP/stream parsing boundary.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchGraph, fetchNote, parseActivityEvent } from '@gui/api';
import { event, graph, noteContent } from './fixtures';

afterEach(() => vi.unstubAllGlobals());

describe('live graph API boundary', () => {
  it('loads backend note identifiers and rejects HTTP failure instead of making sample data', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(Response.json(graph)).mockResolvedValueOnce(new Response('Unavailable', { status: 503 })));
    expect(await fetchGraph()).toEqual(graph);
    await expect(fetchGraph()).rejects.toThrow();
    const encoded = { ...noteContent(), id: 'Projects/Tribal.md' };
    const fetch = vi.fn().mockResolvedValueOnce(Response.json(encoded)).mockResolvedValueOnce(new Response('', { status: 404 })).mockResolvedValueOnce(Response.json({ ...encoded, markdown: 42 }));
    vi.stubGlobal('fetch', fetch);
    expect(await fetchNote(encoded.id)).toEqual(encoded);
    expect(fetch).toHaveBeenCalledWith('/api/notes/Projects%2FTribal.md', expect.any(Object));
    await expect(fetchNote(encoded.id)).rejects.toThrow(/no longer available/);
    await expect(fetchNote(encoded.id)).rejects.toThrow(/invalid note contents/);
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
