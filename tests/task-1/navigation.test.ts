// Verify preview navigation identifiers and labels stay consistent.
import { NAVIGATION_ITEMS } from '@/shared';

describe('shared navigation contract', () => {
  it('keeps the planned local pages in a stable order with unique ids', () => {
    expect(NAVIGATION_ITEMS).toEqual([
      { id: 'overview', label: 'Overview' },
      { id: 'repositories', label: 'Repositories' },
      { id: 'agents-tasks', label: 'Agents and Tasks' },
      { id: 'knowledge-explorer', label: 'Knowledge Explorer' },
      { id: 'settings', label: 'Settings' },
    ]);

    const ids = NAVIGATION_ITEMS.map(({ id }) => id);
    expect(new Set(ids).size).toBe(ids.length);
  });
});
