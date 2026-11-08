// Verify real Chromium graph geometry, overlapping colored strokes, navigation and mobile fit.
import type { Page } from '@playwright/test';
import { expect, test } from './playwright-runtime';
import { event, graph, START } from './fixtures';

async function openGraph(page: Page) {
  await page.route('**/api/graph', (route) => route.fulfill({ json: graph }));
  await page.addInitScript(() => {
    class BrowserStream extends EventTarget {
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSED = 2;
      readyState = 1;
      onopen: ((event: Event) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      onmessage: ((event: MessageEvent) => void) | null = null;
      constructor(_url: string) {
        super();
        Object.assign(window, { tribalTestStream: this });
        setTimeout(() => this.onopen?.(new Event('open')), 0);
      }
      close() { this.readyState = 2; }
      emit(value: unknown) { this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(value) })); }
    }
    Object.assign(window, { EventSource: BrowserStream });
  });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Knowledge explorer' })).toBeVisible();
  await expect(page.locator('.react-flow__node[data-id="note-a"]')).toBeVisible();
  await expect(page.locator('.react-flow__edge')).toHaveCount(2);
}

async function emit(page: Page, value: ReturnType<typeof event>) {
  await page.evaluate((activity) => {
    (window as unknown as { tribalTestStream: { emit: (value: unknown) => void } }).tribalTestStream.emit(activity);
  }, value);
}

test('renders overlapping real edge paths and independently expires each server-time trail', async ({ page }) => {
  await page.clock.setFixedTime(new Date(START));
  await openGraph(page);
  await emit(page, event({ node_ids: ['note-a', 'note-b'], edge_ids: ['link-ab'] }));
  await page.clock.setFixedTime(new Date(START + 4000));
  await emit(page, event({ run_id: 'run-lin', name: 'Lin curator', color: '#39c8ab', message: 'Following repository link', timestamp: new Date(START + 4000).toISOString(), edge_ids: ['link-ab'] }));
  await expect(page.getByRole('region', { name: 'Curator activity' }).getByText('Lin curator')).toBeVisible();
  await expect(page.locator('.react-flow__node[data-id="note-a"]')).toBeVisible();
  await expect(page.locator('.react-flow__edge')).toHaveCount(2);
  const strokes = page.getByTestId('edge-visit');
  await expect(strokes).toHaveCount(2);
  const geometry = await strokes.evaluateAll((paths) => paths.map((path) => ({
    path: path.getAttribute('d'), color: path.getAttribute('stroke'),
    length: (path as SVGPathElement).getTotalLength(),
  })));
  expect(geometry.map(({ color }) => color).sort()).toEqual(['#39c8ab', '#a67aff']);
  expect(geometry.every(({ length }) => Number.isFinite(length) && length > 0)).toBe(true);
  expect(geometry[0].path).not.toEqual(geometry[1].path);
  await expect(page.getByTestId('node-visit')).toHaveCount(3);
  await page.clock.setFixedTime(new Date(START + 10000));
  await expect(strokes).toHaveCount(1);
  await expect(strokes).toHaveAttribute('data-run-id', 'run-lin');
  await expect(strokes).toHaveCSS('opacity', '0.4');
  await page.clock.setFixedTime(new Date(START + 14000));
  await expect(strokes).toHaveCount(0);
  await expect(page.getByTestId('node-visit')).toHaveCount(0);
  await page.locator('.react-flow__node[data-id="note-a"]').click();
  await expect(page.getByRole('region', { name: 'Note details' }).getByText('decisions/storage.md')).toBeVisible();
  const viewport = page.locator('.react-flow__viewport');
  const before = await viewport.getAttribute('style');
  await page.getByRole('button', { name: /^Zoom In$/i }).click();
  await expect.poll(() => viewport.getAttribute('style')).not.toEqual(before);
});

test('keeps the note browser and inspector usable at 390px with reduced motion', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await openGraph(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const browser = page.getByRole('complementary', { name: 'Note browser' });
  await browser.getByRole('button', { name: /Repository guide/ }).click();
  await expect(page.getByRole('region', { name: 'Note details' }).getByText('guides/repository.md')).toBeVisible();
  await page.getByRole('searchbox', { name: 'Search notes' }).fill('no matching title');
  await expect(browser.getByText(/No notes match/)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('keeps selected graph notes and their links intact when Backspace is pressed', async ({ page }) => {
  await openGraph(page);
  const selected = page.locator('.react-flow__node[data-id="note-a"]');
  await selected.click();
  await expect(page.getByRole('region', { name: 'Note details' }).getByText('decisions/storage.md')).toBeVisible();
  await page.keyboard.press('Backspace');
  await expect(selected).toBeVisible();
  await expect(page.locator('.react-flow__node')).toHaveCount(3);
  await expect(page.locator('.react-flow__edge')).toHaveCount(2);
  await expect(page.getByRole('complementary', { name: 'Note browser' }).getByRole('button', { name: /Storage decision/ })).toBeVisible();
});
