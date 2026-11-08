// Verify class merging preserves conditional styles and conflict resolution.
import { cn } from '@/shared';

describe('shared class name helper', () => {
  it('combines conditional classes and keeps the last conflicting Tailwind utility', () => {
    expect(cn('px-2 text-sm', false && 'hidden', 'px-4', ['font-medium', 'text-base']))
      .toBe('px-4 font-medium text-base');
  });
});
