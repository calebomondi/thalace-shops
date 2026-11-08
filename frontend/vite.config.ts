import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Same-origin API calls in dev: /api/* goes to the FastAPI backend.
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
