import { mergeConfig } from 'vite';
import { defineConfig } from 'vitest/config';
import { fileURLToPath } from 'node:url';
import viteConfig from '../../vite.config.ts';

// The approved shell snapshot predates the sibling theme and control tasks.
// Resolve only those missing imports to lightweight semantic controls so the
// suite exercises the real App component without changing project config.
const missingSiblingStubs = {
  name: 'task-4-missing-sibling-stubs',
  enforce: 'pre' as const,
  resolveId(source: string) {
    if (source === '@/components/ui' || source.endsWith('/components/ui')) return '\0task-4-ui-stub';
    if (source === '@/theme/index.css' || source.endsWith('/theme/index.css')) return '\0task-4-theme-stub';
    return null;
  },
  load(id: string) {
    if (id === '\0task-4-theme-stub') return '';
    if (id === '\0task-4-ui-stub') {
      return `
        import { createElement } from 'react';
        export const Button = ({ variant, size, ...props }) => createElement('button', props);
        export const Card = (props) => createElement('section', props);
        export const CardContent = (props) => createElement('div', props);
        export const CardHeader = (props) => createElement('header', props);
        export const CardTitle = (props) => createElement('h2', props);
        export const Input = (props) => createElement('input', props);
      `;
    }
    return null;
  },
};

export default mergeConfig(
  viteConfig,
  defineConfig({
    plugins: [missingSiblingStubs],
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: [fileURLToPath(new URL('../../tests/setup.ts', import.meta.url))],
      include: ['tests/task-4/**/*.test.{ts,tsx}'],
      restoreMocks: true,
      clearMocks: true,
    },
  }),
);
