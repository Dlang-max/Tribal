// Verify real Chromium graph geometry, overlapping colored strokes, navigation and mobile fit.
import type { Page } from '@playwright/test';
import { expect, test } from './playwright-runtime';
import { event, graph, noteContent, START } from './fixtures';

async function openGraph(page: Page) {
  await page.route('**/api/graph', (route) => route.fulfill({ json: graph }));
  await page.route('**/api/notes/**', (route) => {
    const id = decodeURIComponent(new URL(route.request().url()).pathname.slice('/api/notes/'.length));
    return route.fulfill({ json: { ...noteContent(id), markdown: noteContent(id).markdown + '\n' + 'long-token-'.repeat(60) } });
  });
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
  await expect(page.getByRole('region', { name: 'Interactive knowledge graph' })).toBeVisible();
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
  await page.screenshot({ path: '/tmp/tribal-obsidian-curator-overlap.png', fullPage: true });
  await page.clock.setFixedTime(new Date(START + 10000));
  await expect(strokes).toHaveCount(1);
  await expect(strokes).toHaveAttribute('data-run-id', 'run-lin');
  await expect(strokes).toHaveCSS('opacity', '0.4');
  await page.clock.setFixedTime(new Date(START + 14000));
  await expect(strokes).toHaveCount(0);
  await expect(page.getByTestId('node-visit')).toHaveCount(0);
  const viewport = page.locator('.react-flow__viewport');
  const before = await viewport.getAttribute('style');
  await page.getByRole('button', { name: /^Zoom In$/i }).click();
  await expect.poll(() => viewport.getAttribute('style')).not.toEqual(before);
  const zoomed = await viewport.getAttribute('style');
  const dot = page.locator('.react-flow__node[data-id="note-a"]');
  await dot.click();
  await expect(page.getByLabel('Markdown preview')).toContainText('Actual Markdown body');
  await expect(page.getByLabel('Markdown preview').getByRole('table')).toBeVisible();
  await page.screenshot({ path: '/tmp/tribal-markdown-preview-desktop.png', fullPage: true });
  await expect(page.getByRole('region', { name: 'Curator activity' })).toBeVisible();
  await expect(dot).toBeHidden();
  await page.getByLabel('Markdown preview').getByRole('link', { name: 'Repository details' }).click();
  await expect(page.getByLabel('Markdown preview').getByRole('heading', { level: 1, name: 'Repository guide' })).toBeVisible();
  await page.getByRole('button', { name: /Back to graph/ }).click();
  await expect(dot).toBeVisible();
  await expect(page.locator('.react-flow__node[data-id="note-b"]')).toBeFocused();
  await expect(viewport).toHaveAttribute('style', zoomed!);
  await page.screenshot({ path: '/tmp/tribal-obsidian-graph-desktop.png', fullPage: true });

});

test('keeps graph, Markdown source and curator activity usable at 390px with reduced motion', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await openGraph(page);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const dot = page.locator('.react-flow__node[data-id="note-b"]');
  await dot.focus();
  await page.keyboard.press('Enter');
  const preview = page.getByLabel('Markdown preview');
  await expect(preview.getByRole('heading', { level: 1, name: 'Repository guide' })).toBeVisible();
  await expect(preview.getByRole('checkbox', { checked: true })).toBeDisabled();
  await expect(preview.locator('script')).toHaveCount(0);
  await expect(preview.getByText('Unsafe link')).not.toHaveAttribute('href', /^javascript:/);
  await page.screenshot({ path: '/tmp/tribal-markdown-preview-mobile.png', fullPage: true });
  const scrollTop = await preview.evaluate((element) => { element.scrollTop = 240; return element.scrollTop; });
  await emit(page, event());
  await expect(preview).toHaveJSProperty('scrollTop', scrollTop);
  const table = preview.getByRole('region', { name: 'Markdown table' });
  expect(await table.evaluate((element) => element.clientWidth <= element.parentElement!.clientWidth)).toBe(true);
  expect(await table.evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(true);
  const code = preview.getByLabel('Code block');
  await expect.poll(() => code.evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(true);
  expect(await preview.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
  await page.getByRole('button', { name: 'Source', exact: true }).click();
  await expect(page.getByLabel('Markdown source')).toContainText('# Repository guide');
  await expect(page.getByRole('region', { name: 'Curator activity' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  const source = page.getByLabel('Markdown source');
  expect(await source.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
  await page.screenshot({ path: '/tmp/tribal-obsidian-reader-mobile.png', fullPage: true });
  await page.keyboard.press('Escape');
  await expect(page.getByRole('region', { name: 'Note contents' })).toHaveCount(0);
  await expect(dot).toBeVisible();
  await expect(dot).toBeFocused();
});

test('keeps selected graph notes and their links intact when Backspace is pressed', async ({ page }) => {
  await openGraph(page);
  const selected = page.locator('.react-flow__node[data-id="note-a"]');
  await selected.click();
  await expect(page.getByLabel('Markdown preview').getByRole('heading', { level: 1, name: 'Storage decision' })).toBeVisible();
  await page.getByRole('button', { name: /Back to graph/ }).click();
  await page.keyboard.press('Backspace');
  await expect(selected).toBeVisible();
  await expect(page.locator('.react-flow__node')).toHaveCount(3);
  await expect(page.locator('.react-flow__edge')).toHaveCount(2);
  await expect(selected).toBeFocused();
  await expect(page.locator('.react-flow__background')).toHaveCount(0);
  await expect(page.locator('.react-flow__edge path[marker-end]')).toHaveCount(0);
});
