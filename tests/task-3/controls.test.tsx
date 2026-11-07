import { useState } from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui';

describe('Button', () => {
  it('preserves button semantics, disabled behavior, and renders as a link when requested', async () => {
    const user = userEvent.setup();
    let clicks = 0;

    render(
      <>
        <Button disabled onClick={() => clicks++}>Unavailable</Button>
        <Button asChild>
          <a href="/repositories">Repositories</a>
        </Button>
      </>,
    );

    const unavailableButton = screen.getByRole('button', { name: 'Unavailable' });
    expect(unavailableButton).toBeDisabled();
    await user.click(unavailableButton);
    expect(clicks).toBe(0);
    expect(screen.getByRole('link', { name: 'Repositories' })).toHaveAttribute('href', '/repositories');
  });
});

describe('Input', () => {
  it('connects a label to the input and accepts user-entered text', async () => {
    const user = userEvent.setup();

    function SearchField() {
      const [query, setQuery] = useState('');
      return (
        <>
          <label htmlFor="repository-search">Search repositories</label>
          <Input id="repository-search" value={query} onChange={(event) => setQuery(event.target.value)} />
          <output aria-label="Current query">{query}</output>
        </>
      );
    }

    render(<SearchField />);

    const input = screen.getByRole('textbox', { name: 'Search repositories' });
    await user.type(input, 'tribal');

    expect(input).toHaveValue('tribal');
    expect(screen.getByLabelText('Current query')).toHaveTextContent('tribal');
  });
});

describe('Card', () => {
  it('renders its visible heading and content', () => {
    render(
      <Card>
        <CardHeader><CardTitle>Repository summary</CardTitle></CardHeader>
        <CardContent>3 repositories connected</CardContent>
      </Card>,
    );

    expect(screen.getByRole('heading', { name: 'Repository summary' })).toBeInTheDocument();
    expect(screen.getByText('3 repositories connected')).toBeInTheDocument();
  });
});

describe('Tabs', () => {
  it('supports accessible arrow-key navigation and exposes only the active panel', async () => {
    const user = userEvent.setup();

    render(
      <Tabs defaultValue="repositories">
        <TabsList aria-label="Workspace views">
          <TabsTrigger value="repositories">Repositories</TabsTrigger>
          <TabsTrigger value="agents">Agents</TabsTrigger>
        </TabsList>
        <TabsContent value="repositories">Repository list</TabsContent>
        <TabsContent value="agents">Agent list</TabsContent>
      </Tabs>,
    );

    const repositoriesTab = screen.getByRole('tab', { name: 'Repositories' });
    expect(repositoriesTab).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Repository list');

    repositoriesTab.focus();
    await user.keyboard('{ArrowRight}');

    expect(screen.getByRole('tab', { name: 'Agents' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel')).toHaveTextContent('Agent list');
    expect(screen.queryByText('Repository list')).not.toBeInTheDocument();
  });
});

describe('Select', () => {
  it('opens from the combobox and lets keyboard users choose an option', async () => {
    const user = userEvent.setup();

    function RepositoryFilter() {
      const [filter, setFilter] = useState('all');
      return (
        <Select value={filter} onValueChange={setFilter}>
          <SelectTrigger aria-label="Repository filter">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All repositories</SelectItem>
            <SelectItem value="active">Active repositories</SelectItem>
          </SelectContent>
        </Select>
      );
    }

    render(<RepositoryFilter />);

    const filter = screen.getByRole('combobox', { name: 'Repository filter' });
    expect(filter).toHaveTextContent('All repositories');
    // jsdom omits this layout API; Radix calls it when focusing the active option.
    const originalScrollIntoView = HTMLElement.prototype.scrollIntoView;
    HTMLElement.prototype.scrollIntoView = () => {};
    try {
      filter.focus();
      await user.keyboard('{Enter}');
      expect(screen.getByRole('listbox')).toBeInTheDocument();
      await user.keyboard('{ArrowDown}{Enter}');

      expect(screen.getByRole('combobox', { name: 'Repository filter' })).toHaveTextContent('Active repositories');
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    } finally {
      HTMLElement.prototype.scrollIntoView = originalScrollIntoView;
    }
  });
});
