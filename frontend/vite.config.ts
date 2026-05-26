import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// Dev: Vite proxies /api/* to the backend so the browser sees a same-origin call
// and we sidestep CORS during local dev. Production routing is handled by the
// reverse proxy (chunk 11).
//
// VITE_PROXY_TARGET points at the backend. Native dev keeps the default
// (http://127.0.0.1:8000); docker-compose sets it to http://backend:8000.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const proxyTarget = env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000'

  return {
    plugins: [react()],
    server: {
      host: true,
      port: 5173,
      strictPort: true,
      proxy: {
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
    },
  }
})
