// Resolve browser test APIs from the GUI package's installed development dependencies.
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const sourceDir = process.env.TRIBAL_GUI_SOURCE_DIR ?? fileURLToPath(new URL('../../src/knowledge-base-gui', import.meta.url));
export const { test, expect } = createRequire(`${sourceDir}/package.json`)('@playwright/test') as typeof import('@playwright/test');
