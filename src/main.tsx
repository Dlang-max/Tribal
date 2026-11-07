import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from '@/app/App';
import { KnowledgeExplorer } from '@/features/knowledge-explorer/KnowledgeExplorer';
import '@/theme/index.css';

const root = document.getElementById('root');

if (!root) {
  throw new Error('Tribal requires a root element.');
}

createRoot(root).render(
  <StrictMode>
    <App knowledgeExplorer={<KnowledgeExplorer />} />
  </StrictMode>,
);
