import { act, screen } from '@testing-library/react';

describe('frontend bootstrap', () => {
  it('renders the informative local foundation placeholder', async () => {
    document.body.innerHTML = '<div id="root"></div>';

    await act(async () => {
      await import('@/main');
    });

    expect(screen.getByRole('heading', { name: 'Tribal' })).toBeInTheDocument();
    expect(screen.getByText('Shared context for agents and repositories.')).toBeInTheDocument();
    expect(screen.getByText(/Local frontend foundation/)).toBeInTheDocument();
  });
});
