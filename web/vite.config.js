import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// server.py serves web/dist. During development `vite` serves the sources
// and forwards /api and /ws to `python server.py --dev` on port 8000, so
// the browser sees one origin and the session cookie just works.
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      // A new build is fetched in the background and applied on the next
      // load; the operator never sees an "update available" prompt.
      registerType: 'autoUpdate',
      manifest: {
        name: 'MCARSPH AutoShare',
        short_name: 'AutoShare',
        description: 'Remote control for the Facebook automation running on the office PC.',
        display: 'standalone',
        start_url: '/',
        scope: '/',
        theme_color: '#fafafa',
        background_color: '#fafafa',
        icons: [
          { src: 'icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any maskable' },
          { src: 'icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any maskable' },
        ],
      },
      workbox: {
        // Precache the app shell only. The API is never cached: a stale
        // count or a replayed command is worse than the offline banner.
        globPatterns: ['**/*.{js,css,html,png,webmanifest}'],
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//, /^\/ws/],
        runtimeCaching: [],
      },
    }),
  ],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/ws': { target: 'http://127.0.0.1:8000', ws: true },
    },
  },
})
