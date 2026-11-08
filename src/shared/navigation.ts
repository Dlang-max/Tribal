/** Stable page IDs for local navigation; these are not backend routes. */
export const NAVIGATION_ITEMS = [
  { id: 'overview', label: 'Overview' },
  { id: 'repositories', label: 'Repositories' },
  { id: 'agents-tasks', label: 'Agents and Tasks' },
  { id: 'knowledge-explorer', label: 'Knowledge Explorer' },
  { id: 'settings', label: 'Settings' },
] as const;

export type NavigationItem = (typeof NAVIGATION_ITEMS)[number];
export type NavigationId = NavigationItem['id'];
