// Connect graph snapshots and native reconnecting SSE activity with complete cleanup.
import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchGraph, parseActivityEvent } from './api';
import { applyActivityEvent, emptyActivityState, pruneActivity } from './activity';
import type { GraphSnapshot } from './types';

export function useKnowledgeBase() {
  const [graph, setGraph] = useState<GraphSnapshot | null>(null);
  const [graphError, setGraphError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [activity, setActivity] = useState(emptyActivityState);
  const [now, setNow] = useState(Date.now);
  const [streamStatus, setStreamStatus] = useState<'connecting' | 'connected' | 'reconnecting' | 'error'>('connecting');
  const [streamError, setStreamError] = useState<string | null>(null);
  const [connection, setConnection] = useState(0);
  const refreshRef = useRef<() => void>(() => {});
  const refresh = useCallback(() => refreshRef.current(), []);
  const reconnect = useCallback(() => setConnection((value) => value + 1), []);

  useEffect(() => {
    let active = true;
    let request: AbortController | undefined;
    let source: EventSource | undefined;
    const load = async () => {
      request?.abort();
      const current = new AbortController();
      request = current;
      setLoading(true);
      setGraphError(null);
      try {
        const snapshot = await fetchGraph(current.signal);
        if (active && request === current) setGraph(snapshot);
      } catch (error) {
        if (active && request === current && !current.signal.aborted) {
          setGraphError(error instanceof Error ? error.message : 'Unable to load the knowledge graph.');
        }
      } finally {
        if (active && request === current) setLoading(false);
      }
    };
    refreshRef.current = () => { void load(); };
    void load();
    setStreamStatus('connecting');
    setStreamError(null);
    try {
      source = new EventSource('/api/activity');
      source.onopen = () => {
        if (!active) return;
        setStreamStatus('connected');
        setStreamError(null);
        void load();
      };
      source.onmessage = (message) => {
        if (!active) return;
        try {
          const event = parseActivityEvent(JSON.parse(message.data));
          setActivity((state) => applyActivityEvent(state, event));
          setStreamError(null);
          if (event.type === 'graph_changed') void load();
        } catch (error) {
          setStreamError(error instanceof Error ? error.message : 'Unable to read an activity event.');
        }
      };
      source.onerror = () => {
        if (!active) return;
        const closed = source?.readyState === 2;
        setStreamStatus(closed ? 'error' : 'reconnecting');
        setStreamError(closed ? 'Activity stream closed. Reconnect to resume live activity.' : 'Activity connection lost. Reconnecting automatically…');
      };
    } catch (error) {
      setStreamStatus('error');
      setStreamError(error instanceof Error ? error.message : 'Activity streaming is unavailable.');
    }
    const clock = window.setInterval(() => {
      const time = Date.now();
      setNow(time);
      setActivity((state) => pruneActivity(state, time));
    }, 100);
    return () => {
      active = false;
      refreshRef.current = () => {};
      request?.abort();
      source?.close();
      window.clearInterval(clock);
    };
  }, [connection]);

  return { graph, graphError, loading, streamStatus, streamError, activity, now, refresh, reconnect };
}
