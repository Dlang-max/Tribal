// Run the standalone preview tests independently of the live dashboard suite.
import { mergeConfig } from 'vite';
import { defineConfig } from 'vitest/config';
import viteConfig from './vite.config.ts';

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./tests/setup.ts'],
      include: ['tests/task-*/**/*.test.{ts,tsx}'],
      exclude: ['**/node_modules/**', '**/dist/**', '**/.git/**'],
      restoreMocks: true,
      clearMocks: true,
    },
  }),
);
