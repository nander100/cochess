/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Required for SharedArrayBuffer, which multi-threaded Stockfish WASM needs (SPEC §4.1).
const crossOriginIsolation = {
  'Cross-Origin-Opener-Policy': 'same-origin',
  'Cross-Origin-Embedder-Policy': 'require-corp',
}

const backendUrl = process.env.BACKEND_URL ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    headers: crossOriginIsolation,
    proxy: { '/api': backendUrl },
  },
  preview: {
    headers: crossOriginIsolation,
    proxy: { '/api': backendUrl },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
  },
})
