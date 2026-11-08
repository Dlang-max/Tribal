// Run independent live graph behavior tests against the real React components.
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';

const sourceDir = process.env.TRIBAL_GUI_SOURCE_DIR ?? fileURLToPath(new URL('../../src/knowledge-base-gui', import.meta.url));
const packageRequire = createRequire(`${sourceDir}/package.json`);
const { default: react } = await import(pathToFileURL(packageRequire.resolve('@vitejs/plugin-react')).href);

export default {
  root: fileURLToPath(new URL('../..', import.meta.url)),
  plugins: [react()],
  resolve: {
    alias: [
      { find: '@gui', replacement: sourceDir },
      { find: /^(react|react-dom|vitest|@testing-library\/[^/]+)(\/.*)?$/, replacement: `${sourceDir}/node_modules/$1$2` },
    ],
  },
  test: {
    environment: 'jsdom',
    include: ['tests/knowledge_base_gui/**/*.test.{ts,tsx}'],
    setupFiles: ['tests/knowledge_base_gui/setup.ts'],
    restoreMocks: true,
    clearMocks: true,
  },
};
