// Exercise the real live knowledge page with concurrent streams, graph updates, and cleanup.
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '@gui/App';
import { event, graph, START } from './fixtures';
import { ControlledEventSource, flush, installNetwork, stream } from './network-boundary';

const browser = () => within(screen.getByRole('complementary', { name: 'Note browser' }));
const visits = (kind: 'node' | 'edge', id: string) => screen.queryAllByTestId(`${kind}-visit`).filter((visit) => visit.dataset.targetId === id);

beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(START); });

describe('live knowledge explorer', () => {
  it('renders concurrent curator names, current work, and independently fading real graph overlays', async () => {
    installNetwork();
    render(<App />);
    await flush();
    act(() => {
      stream().open();
      stream().emit(event({ node_ids: ['note-a', 'note-b'], edge_ids: ['link-ab'] }));
    });
    await flush();
    act(() => {
      vi.advanceTimersByTime(4000);
      stream().emit(event({ run_id: 'run-lin', name: 'Lin curator', color: '#39c8ab', message: 'Following the repository link', timestamp: new Date(START + 4000).toISOString(), edge_ids: ['link-ab'] }));
    });
    await flush();
    const activity = screen.getByRole('region', { name: 'Curator activity' });
    expect(within(activity).getByText('Ada curator')).toBeVisible();
    expect(within(activity).getByText('Lin curator')).toBeVisible();
    expect(within(activity).getByText('Following the repository link')).toBeVisible();
    expect(visits('node', 'note-a').map((visit) => visit.dataset.runId).sort()).toEqual(['run-ada', 'run-lin']);
    expect(visits('edge', 'link-ab').map((visit) => visit.dataset.color).sort()).toEqual(['#39c8ab', '#a67aff']);
    expect(visits('edge', 'link-bc')).toEqual([]);
    act(() => vi.advanceTimersByTime(6000));
    await flush();
    expect(visits('node', 'note-a')).toHaveLength(1);
    expect(visits('node', 'note-a')[0]).toHaveAttribute('data-run-id', 'run-lin');
    expect(Number(visits('edge', 'link-ab')[0].dataset.opacity)).toBeCloseTo(0.4, 1);
    expect(visits('edge', 'link-ab')[0]).toHaveStyle({ opacity: '0.4' });
    act(() => vi.advanceTimersByTime(4000));
    await flush();
    expect(visits('node', 'note-a')).toEqual([]);
    expect(visits('edge', 'link-ab')).toEqual([]);
  });

  it('shows done/failed outcomes and keeps the last observed task for each run', async () => {
    installNetwork();
    render(<App />);
    await flush();
    act(() => {
      stream().emit(event({ type: 'run_finished', status: 'done', message: 'Context ready', node_ids: [] }));
      stream().emit(event({ type: 'run_failed', status: 'failed', run_id: 'run-lin', name: 'Lin curator', color: '#39c8ab', message: 'Curator exited', node_ids: [] }));
    });
    const rows = screen.getAllByTestId('curator-run');
    expect(rows.find((row) => row.dataset.runId === 'run-ada')).toHaveAttribute('data-status', 'done');
    expect(rows.find((row) => row.dataset.runId === 'run-lin')).toHaveAttribute('data-status', 'failed');
    expect(screen.getByText('Context ready')).toBeVisible();
    expect(screen.getByText('Curator exited')).toBeVisible();
  });

  it('filters real notes and inspects the selected note path and linked neighbor', async () => {
    installNetwork();
    render(<App />);
    await flush();
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search notes' }), { target: { value: 'Storage' } });
    const select = browser().getByRole('button', { name: /Storage decision/ });
    fireEvent.click(select);
    const details = screen.getByRole('region', { name: 'Note details' });
    expect(within(details).getByText('decisions/storage.md')).toBeVisible();
    expect(within(details).getByRole('button', { name: /Repository guide/ })).toBeVisible();
    fireEvent.change(screen.getByRole('searchbox', { name: 'Search notes' }), { target: { value: '' } });
    fireEvent.change(screen.getByRole('combobox', { name: 'Note type' }), { target: { value: 'finding' } });
    expect(browser().getByRole('button', { name: /Published finding/ })).toBeVisible();
    expect(browser().queryByRole('button', { name: /Storage decision/ })).not.toBeInTheDocument();
  });

  it('reports an honestly empty graph', async () => {
    installNetwork({ project_id: 'empty-project', nodes: [], edges: [] });
    render(<App />);
    await flush();
    expect(browser().getByText(/no notes/i)).toBeVisible();
    expect(browser().queryByRole('button', { name: /Storage decision/ })).not.toBeInTheDocument();
  });

  it('reports initial network failure and recovers through the refresh control', async () => {
    const network = installNetwork();
    network.fetch.mockRejectedValueOnce(new Error('Graph server unreachable'));
    render(<App />);
    await flush();
    expect(screen.getByText(/Graph server unreachable/)).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: 'Refresh graph' }));
    await flush();
    expect(browser().getByRole('button', { name: /Storage decision/ })).toBeVisible();
  });

  it('refreshes after graph changes and reconnect, while keeping the snapshot on refresh failure', async () => {
    const network = installNetwork();
    render(<App />);
    await flush();
    network.fetch.mockResolvedValueOnce(Response.json({ ...graph, nodes: [...graph.nodes, { id: 'note-new', title: 'Newly published note', type: 'guide', path: 'guides/new.md' }] }));
    act(() => stream().emit(event({ type: 'graph_changed', node_ids: [] })));
    await flush();
    expect(browser().getByRole('button', { name: /Newly published note/ })).toBeVisible();
    act(() => stream().fail());
    expect(screen.getByText(/^Activity reconnecting$/i)).toBeVisible();
    network.fetch.mockResolvedValueOnce(Response.json({ ...graph, nodes: graph.nodes.filter((note) => note.id !== 'note-c'), edges: [graph.edges[0]] }));
    act(() => stream().open());
    await flush();
    expect(browser().queryByRole('button', { name: /Published finding/ })).not.toBeInTheDocument();
    network.fetch.mockRejectedValueOnce(new Error('Refresh unavailable'));
    fireEvent.click(screen.getByRole('button', { name: 'Refresh graph' }));
    await flush();
    expect(screen.getByText(/Refresh unavailable/)).toBeVisible();
    expect(browser().getByRole('button', { name: /Storage decision/ })).toBeVisible();
  });

  it('surfaces malformed stream events without losing the usable graph', async () => {
    installNetwork();
    render(<App />);
    await flush();
    act(() => stream().emit('{"type":"invented"}'));
    expect(screen.getByText(/invalid.*event|malformed.*event/i)).toBeVisible();
    expect(browser().getByRole('button', { name: /Storage decision/ })).toBeVisible();
    act(() => stream().emit(event()));
    expect(screen.getByText('Ada curator')).toBeVisible();
  });

  it('aborts in-flight graph requests and closes the activity subscription on unmount', async () => {
    const network = installNetwork();
    network.fetch.mockImplementationOnce(async (_url, options) => {
      network.requests.push({ signal: options?.signal });
      return new Promise<Response>(() => {});
    });
    const view = render(<App />);
    await flush();
    const source = stream();
    expect(source.url).toBe('/api/activity');
    const signal = network.requests[0].signal;
    expect(signal?.aborted).toBe(false);
    view.unmount();
    expect(source.closed).toBe(true);
    expect(signal?.aborted).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
    expect(ControlledEventSource.instances).toHaveLength(1);
  });

  it('ignores an older snapshot that arrives after a newer graph refresh', async () => {
    const network = installNetwork();
    let resolveOlder!: (value: Response) => void;
    network.fetch.mockImplementationOnce(async () => new Promise<Response>((resolve) => { resolveOlder = resolve; }));
    render(<App />);
    await flush();
    network.fetch.mockResolvedValueOnce(Response.json({ ...graph, nodes: [...graph.nodes, { id: 'latest', title: 'Latest published note', type: 'guide', path: 'guides/latest.md' }] }));
    act(() => stream().emit(event({ type: 'graph_changed', node_ids: [] })));
    await flush();
    expect(browser().getByRole('button', { name: /Latest published note/ })).toBeVisible();
    resolveOlder(Response.json(graph));
    await flush();
    expect(browser().getByRole('button', { name: /Latest published note/ })).toBeVisible();
  });

  it('offers recovery for a closed stream without hiding the loaded graph', async () => {
    installNetwork();
    render(<App />);
    await flush();
    const original = stream();
    act(() => original.fail(true));
    expect(screen.getByText(/^Activity disconnected$/i)).toBeVisible();
    expect(browser().getByRole('button', { name: /Storage decision/ })).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: /Reconnect activity/ }));
    await flush();
    expect(original.closed).toBe(true);
    expect(stream()).not.toBe(original);
    act(() => stream().open());
    await flush();
    expect(screen.getByText(/Live activity connected/i)).toBeVisible();
  });
});
