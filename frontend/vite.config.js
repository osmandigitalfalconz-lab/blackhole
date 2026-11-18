import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The Flask backend serves the built output (frontend/dist) at "/",
// so the default base "/" and the default outDir "dist" are correct.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  // Local dev only: `npm run dev` serves the React app on :5173 and
  // forwards API calls to the Flask backend on :5000.
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:5000',
    },
  },
})
