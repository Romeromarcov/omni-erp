import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// BACKEND_URL puede venir del entorno:
//   - Local dev:  no se setea → default localhost:8000
//   - Docker dev: se setea como http://backend:8000 en docker-compose.yml
const backendUrl = process.env.BACKEND_URL ?? 'http://localhost:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: backendUrl,
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
