import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// Backend for `npm run dev`. Like nginx in Docker: /api/* goes to the backend
// with /api stripped, so the frontend and the API share one origin
// (http://localhost:5173) and the session cookie works without CORS.
const backendUrl = process.env.VITE_BACKEND_URL ?? 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': {
        target: backendUrl,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
});
