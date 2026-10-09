import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

/**
 * Dev server forwards backend API and WebSocket traffic to the FastAPI app
 * (uvicorn on :8000). Backend routes mount at the root — no /api prefix — so
 * each path is proxied individually. Production builds use VITE_API_URL to
 * point at the deployed backend instead.
 */
const API_TARGET = 'http://127.0.0.1:8000'

/**
 * Frontend routes that collide with backend API paths (React Router serves
 * them client-side). A browser refresh navigates with `Accept: text/html`;
 * without this middleware the proxy would forward the document request to
 * FastAPI and show raw JSON (e.g. `{"detail":"Not Found"}`) instead of the
 * app. Rewriting those navigations to `/index.html` lets Vite's SPA fallback
 * serve the app while in-app `fetch()` calls (any JSON accept header) still
 * proxy.
 */
const SPA_ROUTE_PATHS = ['/dashboard', '/incidents', '/services', '/workflow']

function spaRefreshFallback(): Plugin {
  return {
    name: 'sift-spa-refresh-fallback',
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        if (String(req.headers.accept ?? '').includes('text/html')) {
          const url = req.url ?? ''
          if (SPA_ROUTE_PATHS.some((route) => url === route || url.startsWith(`${route}/`))) {
            req.url = '/index.html'
          }
        }
        next()
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), spaRefreshFallback()],
  server: {
    port: 3001,
    proxy: {
      '/incidents': { target: API_TARGET, changeOrigin: true },
      '/dashboard': { target: API_TARGET, changeOrigin: true },
      '/services': { target: API_TARGET, changeOrigin: true },
      '/service-registry': { target: API_TARGET, changeOrigin: true },
      '/auth': { target: API_TARGET, changeOrigin: true },
      '/health': { target: API_TARGET, changeOrigin: true },
      '/traces': { target: API_TARGET, changeOrigin: true },
      '/notifications': { target: API_TARGET, changeOrigin: true },
      '/kg-bootstrap': { target: API_TARGET, changeOrigin: true },
      '/kg-proposals': { target: API_TARGET, changeOrigin: true },
      '/onboarding': { target: API_TARGET, changeOrigin: true },
      '/ws': { target: API_TARGET, changeOrigin: true, ws: true },
    },
  },
})
