import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { KnowledgeExplorer } from '@/features/knowledge-explorer/KnowledgeExplorer';

// React Flow relies on ResizeObserver and measured canvas geometry. Keep the
// alternative list and inspector real while isolating only that visual canvas.
vi.mock('@xyflow/react', async () => {
  const React = await import('react');
  return {
    Background: () => null,
    Controls: () => null,
    MiniMap: () => null,
    ReactFlow: ({ children }: { children?: React.ReactNode }) => React.createElement('div', { 'aria-label': 'Interactive knowledge graph' }, children),
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
    expect(screen.getByRole('button', { name: /Repository context ontology/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Codex assistant/ })).not.toBeInTheDocument();

    await user.clear(screen.getByRole('searchbox', { name: 'Search entities' }));
    await user.click(screen.getByRole('radio', { name: 'Events' }));
    expect(screen.getByRole('button', { name: /Graph approach selected/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Tribal repository/ })).not.toBeInTheDocument();
    expect(screen.getByText('No relationships between these entities.')).toBeInTheDocument();
  });

  it('resets search, kind filter, and selection when the project changes', async () => {
    const user = userEvent.setup();
    render(<KnowledgeExplorer />);

    const browser = screen.getByRole('complementary', { name: 'Graph browser' });
    const entities = within(browser.querySelector('.ke-list-section') as HTMLElement);
    await user.click(entities.getByRole('button', { name: /Codex assistant/ }));
    expect(screen.getByRole('heading', { name: 'Codex assistant' })).toBeInTheDocument();
    await user.type(screen.getByRole('searchbox', { name: 'Search entities' }), 'missing');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Choose project' }), 'field-notes');

    expect(screen.getByRole('searchbox', { name: 'Search entities' })).toHaveValue('');
    expect(screen.getByRole('radio', { name: 'All' })).toBeChecked();
    expect(screen.getByText('Illustrative context for a small research project.')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Inspect the graph' })).toBeInTheDocument();
    const fieldNotesBrowser = screen.getByRole('complementary', { name: 'Graph browser' });
    expect(within(fieldNotesBrowser.querySelector('.ke-list-section') as HTMLElement).getByText('Maya Chen')).toBeInTheDocument();
  });

  it('selects an entity from the keyboard-operable list and displays arbitrary fields', async () => {
    const user = userEvent.setup();
    render(<KnowledgeExplorer />);

    const browser = screen.getByRole('complementary', { name: 'Graph browser' });
    const entity = within(browser.querySelector('.ke-list-section') as HTMLElement).getByRole('button', { name: /Codex assistant/ });
    entity.focus();
    await user.keyboard('{Enter}');

    const inspector = screen.getByRole('complementary', { name: 'Selection details' });
    expect(within(inspector).getByRole('heading', { name: 'Codex assistant' })).toBeInTheDocument();
    expect(within(inspector).getByText('provider')).toBeInTheDocument();
    expect(within(inspector).getByText('OpenAI')).toBeInTheDocument();
    expect(within(inspector).getByText('capabilities')).toBeInTheDocument();
    expect(within(inspector).getByText(/code review/)).toBeInTheDocument();
  });

  it('inspects a relationship and exposes its source and target endpoints', async () => {
    const user = userEvent.setup();
    render(<KnowledgeExplorer />);

    await user.click(screen.getByRole('button', { name: /Contains.*Tribal repository.*Repository context ontology/ }));

    const inspector = screen.getByRole('complementary', { name: 'Selection details' });
    expect(within(inspector).getByRole('heading', { name: 'Contains' })).toBeInTheDocument();
    expect(within(inspector).getByText('source')).toBeInTheDocument();
    expect(within(inspector).getByText('repo-tribal', { selector: '.ke-endpoints code' })).toBeInTheDocument();
    expect(within(inspector).getByText('target', { selector: '.ke-field dt' })).toBeInTheDocument();
    expect(within(inspector).getByText('doc-ontology', { selector: '.ke-endpoints code' })).toBeInTheDocument();
    const endpointFields = inspector.querySelector('.ke-endpoints');
    expect(endpointFields?.textContent).toContain('SourceTribal repository');
    expect(endpointFields?.textContent).toContain('TargetRepository context ontology');
  });

  it('navigates from an inspected entity to a related entity and relationship', async () => {
    const user = userEvent.setup();
    render(<KnowledgeExplorer />);

    const browser = screen.getByRole('complementary', { name: 'Graph browser' });
    const entities = within(browser.querySelector('.ke-list-section') as HTMLElement);
    await user.click(entities.getByText('Tribal repository').closest('button') as HTMLButtonElement);
    const inspector = screen.getByRole('complementary', { name: 'Selection details' });
    await user.click(within(inspector).getByRole('button', { name: /Repository context ontology/ }));
    expect(within(inspector).getByRole('heading', { name: 'Repository context ontology' })).toBeInTheDocument();

    const firstConnection = within(inspector.querySelector('.ke-connection-list li') as HTMLElement);
    await user.click(firstConnection.getByRole('button', { name: 'Inspect relationship' }));
    expect(within(inspector).getByRole('heading', { name: 'Contains' })).toBeInTheDocument();
  });

  it('does not expose graph editing or connection creation controls', () => {
    render(<KnowledgeExplorer />);

    expect(screen.queryByRole('button', { name: /^(Edit|Add|Create|Connect)(\b| )/i })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/add edge|connect nodes|edit graph/i)).not.toBeInTheDocument();
  });
});
