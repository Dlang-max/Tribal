import { readFileSync, statSync } from 'node:fs';
import { resolve } from 'node:path';

const themePath = resolve(process.cwd(), 'src/theme/index.css');
const themeCss = readFileSync(themePath, 'utf8');

describe('global theme stylesheet', () => {
  it('defines the approved Tribal dark palette as shadcn theme variables', () => {
    const expectedVariables: Record<string, string> = {
      '--background': '#09080d',
      '--foreground': '#f4f0fa',
      '--card': '#251833',
      '--primary': '#a67aff',
      '--primary-foreground': '#100b18',
      '--muted-foreground': '#c6bbd3',
      '--ring': '#a67aff',
    };

    for (const [name, value] of Object.entries(expectedVariables)) {
      expect(themeCss).toMatch(new RegExp(`${name}:\\s*${value};`, 'i'));
    }
    expect(themeCss).toContain('@theme inline');
    expect(themeCss).toMatch(/--color-background:\s*var\(--background\)/);
    expect(themeCss).toMatch(/--color-primary:\s*var\(--primary\)/);
  });

  it('declares bundled Inter regular and bold faces with matching local assets', () => {
    const fontFaces = [...themeCss.matchAll(/@font-face\s*\{([^}]+)\}/g)].map(
      ([, declarations]) => declarations,
    );
    const regularFace = fontFaces.find((face) => /font-weight:\s*400/.test(face));
    const boldFace = fontFaces.find((face) => /font-weight:\s*700/.test(face));

    expect(regularFace).toMatch(/font-family:\s*Inter/);
    expect(regularFace).toMatch(/Inter-Regular\.otf/);
    expect(boldFace).toMatch(/font-family:\s*Inter/);
    expect(boldFace).toMatch(/Inter-Bold\.otf/);

    for (const filename of ['Inter-Regular.otf', 'Inter-Bold.otf']) {
      expect(statSync(resolve(process.cwd(), 'src/theme/fonts', filename)).size).toBeGreaterThan(0);
    }
  });

  it('provides visible keyboard focus and a narrow-screen text adjustment', () => {
    expect(themeCss).toMatch(/:focus-visible\s*\{[^}]*outline:\s*2px solid var\(--ring\)/s);
    expect(themeCss).toMatch(/@media\s*\(max-width:\s*640px\)/);
    expect(themeCss).toMatch(/body\s*\{[^}]*font-size:\s*0\.875rem/s);
    expect(themeCss).toMatch(/html\s*\{[^}]*min-width:\s*320px/s);
  });
});
