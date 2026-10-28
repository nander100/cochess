/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'

// Required for SharedArrayBuffer, which multi-threaded Stockfish WASM needs (SPEC §4.1).
const crossOriginIsolation = {
  'Cross-Origin-Opener-Policy': 'same-origin',
  'Cross-Origin-Embedder-Policy': 'require-corp',
}

const backendUrl = process.env.BACKEND_URL ?? 'http://localhost:8000'

// End-to-end tests (E2E_FAKE_ENGINE=1) swap Stockfish for a scripted engine with the same UCI
// protocol, so flows run fast and the same every time. Never set for a real build.
const engineTransport = fileURLToPath(
  new URL(
    process.env.E2E_FAKE_ENGINE === '1' ? './src/test/scriptedEngine.ts' : './src/engine/workerTransport.ts',
    import.meta.url,
  ),
)

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@engine-transport': engineTransport } },
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
    include: ['src/**/*.test.{ts,tsx}'],
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
  },
})
