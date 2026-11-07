import { act, screen } from '@testing-library/react';

describe('frontend bootstrap', () => {
  it('renders the integrated Tribal workspace', async () => {
    document.body.innerHTML = '<div id="root"></div>';

    await act(async () => {
      await import('@/main');
    });

    expect(screen.getByRole('link', { name: 'Tribal home' })).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Main navigation' })).toBeInTheDocument();
  });
});
