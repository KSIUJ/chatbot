import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App';

const root = document.getElementById('root');
if (root === null) throw new Error('Missing #root element in index.html');

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
