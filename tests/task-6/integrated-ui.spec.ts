// Verify the preview navigation and graph interactions in Chromium.
import { expect, test } from '@playwright/test';

test.use({
  launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
    ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH }
    : {},
});

test('workspace navigation reaches each local page template', async ({ page }) => {
  await page.goto('/');

  const pages = [
    { navigation: 'Overview', heading: 'Good morning, Daniel' },
    { navigation: 'Repositories', heading: 'Repositories' },
    { navigation: 'Agents and Tasks', heading: 'Agents and tasks' },
    { navigation: 'Knowledge Explorer', heading: 'Knowledge explorer' },
    { navigation: 'Settings', heading: 'Settings' },
  ];

  for (const item of pages) {
    await page.getByRole('button', { name: item.navigation, exact: true }).click();
    await expect(page.getByRole('heading', { name: item.heading, exact: true })).toBeVisible();
  }
});

test('knowledge explorer supports graph inspection, related-record navigation, and project reset', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Knowledge Explorer', exact: true }).click();

  const browser = page.getByRole('complementary', { name: 'Graph browser' });
  const inspector = page.getByRole('complementary', { name: 'Selection details' });
  const search = page.getByRole('searchbox', { name: 'Search entities' });
  await expect(browser.getByRole('heading', { name: 'Entities 6' })).toBeVisible();

  // A graph node selection populates ontology fields and relationship links.
  await page.locator('.react-flow__node[data-id="agent-codex"]').click();
  await expect(inspector.getByRole('heading', { name: 'Codex sample agent' })).toBeVisible();
  await expect(inspector.getByText('example-session-001')).toBeVisible();

  const sessionLink = inspector.locator('.ke-connection-list li').filter({ hasText: 'To · HasSession' });
  await sessionLink.getByRole('button', { name: /Codex sample session file/ }).click();
  await expect(inspector.getByRole('heading', { name: 'Codex sample session file' })).toBeVisible();
  await expect(inspector.locator('.ke-field-list')).toContainText('2026/11/07/example-session-001.jsonl');

  await browser.locator('.ke-list-section').first().getByRole('button', { name: /Codex sample agent Agent/ }).click();
  await inspector.locator('.ke-connection-list li').filter({ hasText: 'To · WorksOn' }).getByRole('button', { name: /Knowledge explorer WorkItem/ }).click();
  await expect(inspector.getByRole('heading', { name: 'Knowledge explorer' })).toBeVisible();

  const creatorConnection = inspector.locator('.ke-connection-list li').filter({ hasText: 'To · ProducedBy' });
  await expect(creatorConnection.getByRole('button', { name: /Codex sample agent/ })).toBeVisible();
  await creatorConnection.getByRole('button', { name: 'Inspect relationship' }).click();
  await expect(inspector.getByRole('heading', { name: 'ProducedBy', exact: true })).toBeVisible();
  expect(await inspector.locator('.ke-field-list dt').allTextContents()).toEqual(['source', 'target']);
  expect(await inspector.locator('.ke-field-list dd').allTextContents()).toEqual(['task-graph', 'agent-codex']);

  await browser.locator('.ke-list-section').first().getByRole('button', { name: /Knowledge explorer WorkItem/ }).click();
  await inspector.locator('.ke-connection-list li').filter({ hasText: 'To · ProducedBy' }).getByRole('button', { name: /Codex sample agent/ }).click();
  await expect(inspector.getByRole('heading', { name: 'Codex sample agent' })).toBeVisible();

  // The relationship browser exposes the edge record and its directed endpoints.
  await browser.getByRole('button', { name: /References Ontology reference → Tribal repository/ }).click();
  await expect(inspector.getByRole('heading', { name: 'References', exact: true })).toBeVisible();
  await expect(inspector.locator('.ke-endpoints')).toContainText('evidence-ontology');
  await expect(inspector.locator('.ke-endpoints')).toContainText('repo-tribal');

  await search.fill('no matching record');
  await expect(browser.getByText('No entities match this search.')).toBeVisible();
  await page.getByRole('radio', { name: 'Events' }).check();
  await search.fill('work began');
  await expect(browser.getByRole('button', { name: /Knowledge explorer work began/ })).toBeVisible();
  await expect(browser.getByRole('button', { name: /Tribal repository/ })).toHaveCount(0);

  await page.getByRole('combobox', { name: 'Choose project' }).selectOption('field-notes');
  await expect(search).toHaveValue('');
  await expect(page.getByRole('radio', { name: 'All' })).toBeChecked();
  await expect(inspector.getByRole('heading', { name: 'Inspect the graph' })).toBeVisible();
  await expect(browser.locator('.ke-list-section').first().getByRole('button', { name: /Maya Chen \(sample identity\)/ })).toBeVisible();
});

test('graph controls change the viewport and the integrated shell remains keyboard and mobile friendly', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Repositories', exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: 'Repositories', exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Knowledge Explorer', exact: true }).click();
  const canvas = page.locator('.react-flow');
  const viewport = page.locator('.react-flow__viewport');
  const initialTransform = await viewport.getAttribute('style');
  await page.locator('.react-flow__controls-zoomin').click();
  await expect.poll(() => viewport.getAttribute('style')).not.toBe(initialTransform);
  const zoomedTransform = await viewport.getAttribute('style');
  await page.locator('.react-flow__controls-fitview').click();
  await expect.poll(() => viewport.getAttribute('style')).not.toBe(zoomedTransform);
  await page.locator('.react-flow__controls-zoomout').click();
  const beforePan = await viewport.getAttribute('style');
  const canvasBox = await canvas.boundingBox();
  if (!canvasBox) throw new Error('Expected the graph canvas to have a visible viewport.');
  await page.mouse.move(canvasBox.x + canvasBox.width / 2, canvasBox.y + canvasBox.height - 35);
  await page.mouse.down();
  await page.mouse.move(canvasBox.x + canvasBox.width / 2 - 35, canvasBox.y + canvasBox.height - 60, { steps: 5 });
  await page.mouse.up();
  await expect.poll(() => viewport.getAttribute('style')).not.toBe(beforePan);
  await expect(canvas).toBeVisible();

  const keyboardEntity = page.getByRole('complementary', { name: 'Graph browser' }).locator('.ke-list-section').first().getByRole('button', { name: /Codex sample agent/ });
  await keyboardEntity.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('complementary', { name: 'Selection details' }).getByRole('heading', { name: 'Codex sample agent' })).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('heading', { name: 'Knowledge explorer' })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0);
  await expect.poll(() => page.evaluate(() => document.body.scrollWidth - document.body.clientWidth)).toBe(0);
  const theme = await page.evaluate(async () => {
    await document.fonts.ready;
    return {
      fontLoaded: document.fonts.check('14px Inter'),
      fontFamily: getComputedStyle(document.body).fontFamily,
      background: getComputedStyle(document.body).backgroundColor,
    };
  });
  expect(theme.fontLoaded).toBe(true);
  expect(theme.fontFamily).toContain('Inter');
  expect(theme.background).toBe('rgb(9, 8, 13)');
});
