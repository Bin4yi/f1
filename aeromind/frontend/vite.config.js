// Vite proxy configuration for /api and /ws.
import { defineConfig } from 'vite';

export default defineConfig({
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': 'http://backend:8080',
      '/ws': {
        target: 'ws://backend:8080',
        ws: true
      },
      '/aria': {
        target: 'ws://backend:8080',
        ws: true
      },
      '/aria/voice': {
        target: 'ws://backend:8080',
        ws: true
      }
    },
    watch: {
      usePolling: true
    }
  }
});

