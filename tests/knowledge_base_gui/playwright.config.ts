// Run native Chromium graph and responsive layout checks against the live GUI package.
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const sourceDir = process.env.TRIBAL_GUI_SOURCE_DIR ?? fileURLToPath(new URL('../../src/knowledge-base-gui', import.meta.url));
const { defineConfig, devices } = createRequire(`${sourceDir}/package.json`)('@playwright/test');

export default defineConfig({
  testDir: fileURLToPath(new URL('.', import.meta.url)),
  testMatch: '**/*.browser.spec.ts',
  fullyParallel: true,
  retries: 0,
  reporter: 'list',
  outputDir: fileURLToPath(new URL('../../test-results/knowledge-base-gui', import.meta.url)),
  use: {
    baseURL: 'http://127.0.0.1:4187', trace: 'retain-on-failure',
    launchOptions: process.env.TRIBAL_CHROMIUM_EXECUTABLE ? { executablePath: process.env.TRIBAL_CHROMIUM_EXECUTABLE } : {},
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    cwd: sourceDir,
    command: 'npm run dev -- --host 127.0.0.1 --port 4187 --strictPort',
    url: 'http://127.0.0.1:4187',
    reuseExistingServer: false,
  },
});
