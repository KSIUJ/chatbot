import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Backend dla `npm run dev`. Tak jak nginx w Dockerze: /api/* -> backend
// z obcietym /api, wiec frontend i API sa na jednym originie
// (http://localhost:5173) i ciasteczko sesji dziala bez CORS.
const backendUrl = process.env.VITE_BACKEND_URL ?? 'http://127.0.0.1:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: backendUrl,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
