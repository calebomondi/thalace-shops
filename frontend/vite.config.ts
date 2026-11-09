import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Fixed ports, clear of other projects' dev servers on 5173/8000. The
    // Supabase redirect URLs list this port, so it must not drift.
    port: 5180,
    strictPort: true,
    // Cloudflare quick tunnels (cloudflared tunnel --url http://localhost:5180)
    // give an https:// address for testing passkeys; it changes on each start.
    allowedHosts: ['.trycloudflare.com'],
    // Same-origin API calls in dev: /api/* goes to the FastAPI backend.
    proxy: {
      '/api': 'http://localhost:8100',
    },
  },
})
