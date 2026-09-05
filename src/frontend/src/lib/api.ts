// W Dockerze ustawiane na build-time na "/api" (proxy przez nginx frontendu,
// patrz src/frontend/nginx.conf) - dzieki temu frontend zawsze woła wlasny
// origin, zero CORS i zero zaszytego adresu/hosta backendu. Lokalnie
// (npm run dev, bez Dockera) domyslnie trafia wprost do backendu na
// 127.0.0.1:8000.
export const API_BASE_URL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000';
