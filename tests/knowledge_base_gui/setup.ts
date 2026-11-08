// Supply browser layout APIs for real React Flow rendering in jsdom.
import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

Object.defineProperties(HTMLElement.prototype, {
  offsetWidth: { configurable: true, get: () => 800 },
  offsetHeight: { configurable: true, get: () => 400 },
  clientWidth: { configurable: true, get: () => 800 },
  clientHeight: { configurable: true, get: () => 400 },
});

class LayoutObserver {
  private targets = new Set<Element>();
  constructor(private callback: ResizeObserverCallback) {}
  observe(target: Element) {
    this.targets.add(target);
    void Promise.resolve().then(() => {
      if (this.targets.has(target)) this.callback([{ target, contentRect: { width: 800, height: 400 } } as ResizeObserverEntry], this as unknown as ResizeObserver);
    });
  }
  unobserve(target: Element) { this.targets.delete(target); }
  disconnect() { this.targets.clear(); }
}

vi.stubGlobal('ResizeObserver', LayoutObserver);
vi.stubGlobal('DOMMatrixReadOnly', class { m22 = 1; });
Object.defineProperty(window, 'matchMedia', {
  configurable: true,
  value: (query: string) => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {} }),
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.stubGlobal('ResizeObserver', LayoutObserver);
  vi.stubGlobal('DOMMatrixReadOnly', class { m22 = 1; });
});
