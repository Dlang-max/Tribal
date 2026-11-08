// Control graph HTTP responses and native EventSource lifecycle without replacing GUI components.
import { act } from '@testing-library/react';
import { vi } from 'vitest';
import type { ActivityEvent, GraphSnapshot } from '@gui/types';
import { graph, noteContent } from './fixtures';

export class ControlledEventSource {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSED = 2;
  static instances: ControlledEventSource[] = [];
  readonly CONNECTING = 0;
  readonly OPEN = 1;
  readonly CLOSED = 2;
  readyState = 0;
  onopen: ((event: Event) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  closed = false;
  constructor(readonly url: string) { ControlledEventSource.instances.push(this); }
  open() { this.readyState = 1; this.onopen?.(new Event('open')); }
  fail(permanent = false) { this.readyState = permanent ? 2 : 0; this.onerror?.(new Event('error')); }
  emit(value: ActivityEvent | string) {
    this.onmessage?.(new MessageEvent('message', { data: typeof value === 'string' ? value : JSON.stringify(value) }));
  }
  close() { this.closed = true; this.readyState = 2; }
}

export function installNetwork(snapshot: GraphSnapshot = graph) {
  ControlledEventSource.instances = [];
  vi.stubGlobal('EventSource', ControlledEventSource);
  const requests: { signal?: AbortSignal | null }[] = [];
  const fetch = vi.fn(async (url: RequestInfo | URL, options?: RequestInit) => {
    if (String(url).startsWith('/api/notes/')) {
      requests.push({ signal: options?.signal });
      return Response.json(noteContent(decodeURIComponent(String(url).slice('/api/notes/'.length))));
    }
    if (url !== '/api/graph') throw new Error(`Unexpected HTTP request: ${String(url)}`);
    requests.push({ signal: options?.signal });
    return Response.json(snapshot);
  });
  vi.stubGlobal('fetch', fetch);
  return { fetch, requests };
}

export function stream() {
  const source = ControlledEventSource.instances.at(-1);
  if (!source) throw new Error('The real GUI did not subscribe to its activity stream');
  return source;
}

export async function flush() {
  await act(async () => {
    for (let i = 0; i < 12; i++) await Promise.resolve();
  });
}
