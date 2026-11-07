import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { KnowledgeExplorer } from '@/features/knowledge-explorer/KnowledgeExplorer';

const graphHarness = vi.hoisted(() => ({
  latestFlowProps: undefined as {
    fitView?: boolean;
    fitViewOptions?: { padding: number };
    minZoom?: number;
    maxZoom?: number;
    nodesDraggable?: boolean;
    nodesConnectable?: boolean;
    edgesReconnectable?: boolean;
    elementsSelectable?: boolean;
    panOnDrag?: boolean;
    zoomOnScroll?: boolean;
  } | undefined,
  latestControlsProps: undefined as { showInteractive?: boolean } | undefined,
}));

// React Flow relies on ResizeObserver and measured canvas geometry. The harness
// exposes props and canvas callbacks while keeping filtering and inspector state real.
vi.mock('@xyflow/react', async () => {
  const React = await import('react');
  type Node = { id: string };
  type Edge = { id: string };
  type FlowProps = {
    children?: React.ReactNode;
    nodes?: Node[];
    edges?: Edge[];
    fitView?: boolean;
    fitViewOptions?: { padding: number };
    minZoom?: number;
    maxZoom?: number;
    nodesDraggable?: boolean;
    nodesConnectable?: boolean;
    edgesReconnectable?: boolean;
    elementsSelectable?: boolean;
    panOnDrag?: boolean;
    zoomOnScroll?: boolean;
    onNodeClick?: (event: unknown, node: Node) => void;
    onEdgeClick?: (event: unknown, edge: Edge) => void;
  };
  return {
    MarkerType: { ArrowClosed: 'arrowclosed' },
    Background: () => null,
    Controls: (props: { showInteractive?: boolean }) => {
      graphHarness.latestControlsProps = props;
      return React.createElement('div', { role: 'group', 'aria-label': 'Graph controls' }, [
        React.createElement('button', { key: 'zoom-in', type: 'button' }, 'Zoom in'),
        React.createElement('button', { key: 'zoom-out', type: 'button' }, 'Zoom out'),
        React.createElement('button', { key: 'fit-view', type: 'button' }, 'Fit view'),
      ]);
    },
    MiniMap: () => null,
    ReactFlow: (props: FlowProps) => {
      graphHarness.latestFlowProps = props;
      const event = new MouseEvent('click');
      return React.createElement('div', { 'aria-label': 'Graph canvas' }, [
        ...(props.nodes ?? []).map((node) => React.createElement('button', {
          key: node.id,
          type: 'button',
          onClick: () => props.onNodeClick?.(event, node),
        }, `Select graph node ${node.id}`)),
        ...(props.edges ?? []).map((edge) => React.createElement('button', {
          key: edge.id,
          type: 'button',
          onClick: () => props.onEdgeClick?.(event, edge),
        }, `Select graph relationship ${edge.id}`)),
        props.children,
      ]);
    },
  };
});

describe('KnowledgeExplorer', () => {
  it('offers two clearly labeled sample projects', () => {
    render(<KnowledgeExplorer />);

    expect(screen.getByRole('combobox', { name: 'Choose project' })).toHaveValue('tribal-platform');
    expect(screen.getByText('Illustrative context for a shared agent memory platform.')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Field Notes' })).toBeInTheDocument();
    expect(screen.getByText('Sample graphs are illustrative and do not represent live project data.')).toBeInTheDocument();
  });

  it('searches entities and filters them by ontology kind', async () => {
    const user = userEvent.setup();
    render(<KnowledgeExplorer />);

    await user.type(screen.getByRole('searchbox', { name: 'Search entities' }), 'ontology');
    expect(screen.getByRole('button', { name: /Ontology referenceEvidence/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Codex sample agent/ })).not.toBeInTheDocument();

    await user.clear(screen.getByRole('searchbox', { name: 'Search entities' }));
    await user.click(screen.getByRole('radio', { name: 'Events' }));
    expect(screen.getByRole('button', { name: /Knowledge explorer work beganWorkStarted/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Tribal repository/ })).not.toBeInTheDocument();
    expect(screen.getByText('No relationships between these entities.')).toBeInTheDocument();
  });

  it('resets search, kind filter, and selection when the project changes', async () => {
    const user = userEvent.setup();
    render(<KnowledgeExplorer />);

    const browser = screen.getByRole('complementary', { name: 'Graph browser' });
    await user.click(within(browser).getByRole('button', { name: /Codex sample agentAgent/ }));
    expect(screen.getByRole('heading', { name: 'Codex sample agent' })).toBeInTheDocument();
    await user.type(screen.getByRole('searchbox', { name: 'Search entities' }), 'missing');
    await user.click(screen.getByRole('radio', { name: 'Events' }));
    await user.selectOptions(screen.getByRole('combobox', { name: 'Choose project' }), 'field-notes');

    expect(screen.getByRole('searchbox', { name: 'Search entities' })).toHaveValue('');
    expect(screen.getByRole('radio', { name: 'All' })).toBeChecked();
    expect(screen.getByText('Illustrative context for a small research project.')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Inspect the graph' })).toBeInTheDocument();
    const fieldNotesBrowser = screen.getByRole('complementary', { name: 'Graph browser' });
    expect(within(fieldNotesBrowser).getByRole('button', { name: /Maya Chen \(sample identity\)Developer/ })).toBeInTheDocument();
  });

  it('selects an entity from the keyboard-operable list and displays arbitrary fields', async () => {
    const user = userEvent.setup();
    render(<KnowledgeExplorer />);

    const entity = screen.getByRole('button', { name: /Codex sample agentAgent/ });
    entity.focus();
    await user.keyboard('{Enter}');

    const inspector = screen.getByRole('complementary', { name: 'Selection details' });
    expect(within(inspector).getByRole('heading', { name: 'Codex sample agent' })).toBeInTheDocument();
    expect(within(inspector).getByText('sessionId')).toBeInTheDocument();
    expect(within(inspector).getByText('example-session-001')).toBeInTheDocument();
    expect(within(inspector).getByText('description')).toBeInTheDocument();
    expect(within(inspector).getByText(/illustrative agent identity/)).toBeInTheDocument();
  });

  it('inspects a relationship and exposes its source and target endpoints', async () => {
    const user = userEvent.setup();
    render(<KnowledgeExplorer />);

    await user.click(screen.getByRole('button', { name: /References.*Ontology reference.*Tribal repository/ }));

    const inspector = screen.getByRole('complementary', { name: 'Selection details' });
    expect(within(inspector).getByRole('heading', { name: 'References' })).toBeInTheDocument();
    expect(within(inspector).getByRole('heading', { name: 'Relationship fields' })).toBeInTheDocument();
    expect(within(inspector).getByRole('heading', { name: 'Endpoints' })).toBeInTheDocument();
    expect(within(inspector).getAllByRole('term').map((term) => term.textContent)).toEqual([
      'source', 'target', 'Source', 'Target',
    ]);
    expect(within(inspector).getAllByRole('definition').map((definition) => definition.textContent)).toEqual([
      'evidence-ontology', 'repo-tribal', 'Ontology reference', 'Tribal repository',
    ]);
  });

  it('navigates from an inspected entity to a related entity and relationship', async () => {
    const user = userEvent.setup();
    render(<KnowledgeExplorer />);

    await user.click(screen.getByRole('button', { name: /Tribal repositoryRepository/ }));
    const inspector = screen.getByRole('complementary', { name: 'Selection details' });
    await user.click(within(inspector).getByRole('button', { name: /Ontology reference/ }));
    expect(within(inspector).getByRole('heading', { name: 'Ontology reference' })).toBeInTheDocument();

    const referenceConnection = within(inspector).getAllByRole('listitem').find((item) => item.textContent?.includes('References'));
    if (!referenceConnection) throw new Error('Expected the References connection in the inspector.');
    await user.click(within(referenceConnection).getByRole('button', { name: 'Inspect relationship' }));
    expect(within(inspector).getByRole('heading', { name: 'References' })).toBeInTheDocument();
  });

  it('does not expose graph editing or connection creation controls', () => {
    render(<KnowledgeExplorer />);

    expect(screen.queryByRole('button', { name: /^(Edit|Add|Create|Connect)(\b| )/i })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/add edge|connect nodes|edit graph/i)).not.toBeInTheDocument();
  });

  it('configures fit, pan, zoom bounds, controls, and a read-only graph canvas', () => {
    render(<KnowledgeExplorer />);

    const flowProps = graphHarness.latestFlowProps;
    const controlsProps = graphHarness.latestControlsProps;

    expect(flowProps?.fitView).toBe(true);
    expect(flowProps?.fitViewOptions).toEqual({ padding: 0.25 });
    expect(flowProps?.minZoom).toBe(0.25);
    expect(flowProps?.maxZoom).toBe(1.8);
    expect(flowProps?.nodesDraggable).toBe(false);
    expect(flowProps?.nodesConnectable).toBe(false);
    expect(flowProps?.edgesReconnectable).toBe(false);
    expect(flowProps?.elementsSelectable).toBe(true);
    expect(flowProps?.panOnDrag).not.toBe(false);
    expect(flowProps?.zoomOnScroll).not.toBe(false);
    expect(controlsProps?.showInteractive).toBe(false);
    expect(screen.getByRole('group', { name: 'Graph controls' })).toHaveAccessibleName('Graph controls');
    expect(screen.getByRole('button', { name: 'Zoom in' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Zoom out' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Fit view' })).toBeInTheDocument();
    expect(screen.getByText('Drag to pan · scroll to zoom')).toBeInTheDocument();
  });

  it('selects graph nodes and edges through their real inspector callbacks', async () => {
    const user = userEvent.setup();
    render(<KnowledgeExplorer />);

    await user.click(screen.getByRole('button', { name: 'Select graph node agent-codex' }));
    const inspector = screen.getByRole('complementary', { name: 'Selection details' });
    expect(within(inspector).getByRole('heading', { name: 'Codex sample agent' })).toBeInTheDocument();
    expect(within(inspector).getByText('sessionId')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Select graph relationship tribal-r1' }));
    expect(within(inspector).getByRole('heading', { name: 'References' })).toBeInTheDocument();
    expect(within(inspector).getByRole('heading', { name: 'Endpoints' })).toBeInTheDocument();
  });
});
