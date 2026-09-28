import { fileURLToPath, URL } from 'node:url';
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  // loadEnv only reads .env files, so the real environment is consulted first:
  // that is how an end-to-end run points the dev server somewhere else.
  const fileEnv = loadEnv(mode, fileURLToPath(new URL('../..', import.meta.url)), '');
  const read = (key: string, fallback: string): string =>
    process.env[key] ?? fileEnv[key] ?? fallback;

  const apiUrl = read('VITE_API_URL', 'http://localhost:3001');

  return {
    plugins: [react()],
    resolve: {
      alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    },
    define: {
      // The bundle talks to a same-origin /api; the dev server proxies it.
      'import.meta.env.VITE_API_URL': JSON.stringify(''),
    },
    server: {
      // Bound explicitly: without this Vite listens on IPv6 localhost only, and
      // a health check against 127.0.0.1 never connects.
      host: '127.0.0.1',
      port: Number(read('VITE_PORT', '5173')),
      strictPort: true,
      // A same-origin /api during development means no CORS preflight and no
      // hard-coded host in the bundle.
      proxy: {
        '/api': { target: apiUrl, changeOrigin: true },
        '/ws': { target: apiUrl, ws: true, changeOrigin: true },
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: true,
      rollupOptions: {
        output: {
          // The framework changes far less often than the application, so it
          // gets its own chunk and stays in the browser cache across releases.
          manualChunks: {
            react: ['react', 'react-dom', 'react-router-dom'],
            query: ['@tanstack/react-query'],
          },
        },
      },
    },
  };
});
