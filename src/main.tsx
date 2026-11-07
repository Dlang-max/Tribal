import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

const root = document.getElementById('root');

if (!root) {
  throw new Error('Tribal requires a root element.');
}

createRoot(root).render(
  <StrictMode>
    <main>
      <h1>Tribal</h1>
      <p>Shared context for agents and repositories.</p>
      <p>Local frontend foundation. Sample workspace templates are being assembled.</p>
    </main>
  </StrictMode>,
);
