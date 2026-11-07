import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import App from '@/app/App';

const pageNames = ['Overview', 'Repositories', 'Agents and Tasks', 'Knowledge Explorer', 'Settings'] as const;
const pageHeadings: Record<(typeof pageNames)[number], string> = {
  Overview: 'Good morning, Daniel',
  Repositories: 'Repositories',
  'Agents and Tasks': 'Agents and tasks',
  'Knowledge Explorer': 'Knowledge Explorer',
  Settings: 'Settings',
};

function navigateTo(label: (typeof pageNames)[number]) {
  fireEvent.click(screen.getByRole('button', { name: label }));
}

describe('frontend shell', () => {
  it('keeps every workspace destination local and updates the active view', () => {
    render(<App />);
    const navigation = screen.getByRole('navigation', { name: 'Main navigation' });

    for (const page of pageNames) {
      const navButton = within(navigation).getByRole('button', { name: page });
      fireEvent.click(navButton);

      expect(navButton).toHaveAttribute('aria-current', 'page');
      expect(screen.getByRole('heading', { level: 1, name: pageHeadings[page] })).toBeInTheDocument();
      expect(screen.getByText(page, { selector: '.breadcrumb strong' })).toBeInTheDocument();
    }

    expect(window.location.pathname).toBe('/');
    expect(window.location.hash).toBe('');
  });

  it('reaches workspace views through overview calls to action and home', () => {
    render(<App />);

    fireEvent.click(screen.getByRole('button', { name: /view all/i }));
    expect(screen.getByRole('heading', { level: 1, name: 'Repositories' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('link', { name: 'Tribal home' }));
    expect(screen.getByRole('heading', { level: 1, name: 'Good morning, Daniel' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'See agents and tasks' }));
    expect(screen.getByRole('heading', { level: 1, name: 'Agents and tasks' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('link', { name: 'Tribal home' }));
    fireEvent.click(screen.getByRole('button', { name: 'Open Knowledge Explorer' }));
    expect(screen.getByRole('heading', { level: 1, name: 'Knowledge Explorer' })).toBeInTheDocument();
  });

  it('renders an injected explorer inside the explorer view', () => {
    render(<App knowledgeExplorer={<div data-testid="injected-explorer">Live explorer surface</div>} />);

    navigateTo('Knowledge Explorer');

    expect(screen.getByTestId('injected-explorer')).toBeInTheDocument();
    expect(screen.getByText('Live explorer surface')).toBeInTheDocument();
    expect(screen.queryByText('Illustrative graph preview')).not.toBeInTheDocument();
  });

  it('shows an honest local graph preview when no explorer is injected', () => {
    render(<App />);

    navigateTo('Knowledge Explorer');

    expect(screen.getByRole('heading', { level: 1, name: 'Knowledge Explorer' })).toBeInTheDocument();
    expect(screen.getByText('The graph view will appear here. This sample shell does not connect to a knowledge service.')).toBeInTheDocument();
    expect(screen.getByText('Illustrative graph preview')).toBeInTheDocument();
    expect(screen.getByText('Sample data')).toBeInTheDocument();
  });

  it('labels sample content and keeps unavailable integrations disabled', () => {
    render(<App />);

    expect(screen.getByText('Sample data')).toBeInTheDocument();
    expect(screen.getByText('Connected in this sample workspace')).toBeInTheDocument();

    navigateTo('Repositories');
    expect(screen.getByText('3 sample sources')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Connect repository' })).toBeDisabled();
    expect(screen.getByText(/Connecting a live provider is not available in this preview\./)).toBeInTheDocument();

    navigateTo('Agents and Tasks');
    expect(screen.getByText('Local example activity, with no live agent execution.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add agent' })).toBeDisabled();

    navigateTo('Settings');
    expect(screen.getByText('No live connections')).toBeInTheDocument();
    expect(screen.getByText('This preview does not connect to GitHub, agents, or a knowledge service.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Manage integrations' })).toBeDisabled();
  });

  it('gives compact navigation controls accessible names', () => {
    render(<App />);

    const navigation = screen.getByRole('navigation', { name: 'Main navigation' });
    expect(screen.getByRole('button', { name: 'Open navigation' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Tribal home' })).toBeInTheDocument();

    const explorerButton = within(navigation).getByRole('button', { name: 'Knowledge Explorer' });
    fireEvent.click(explorerButton);

    expect(explorerButton).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('heading', { level: 1, name: 'Knowledge Explorer' })).toBeInTheDocument();
  });
});
