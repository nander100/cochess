// Copies the Stockfish lite builds from node_modules into public/engine/ so Vite serves them
// same-origin. Each .wasm must sit next to its .js loader.
import { copyFileSync, existsSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ENGINE_FILES = [
  'stockfish-19-lite.js',
  'stockfish-19-lite.wasm',
  'stockfish-19-lite-single.js',
  'stockfish-19-lite-single.wasm',
]

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const sourceDir = join(root, 'node_modules', 'stockfish', 'bin')
const targetDir = join(root, 'public', 'engine')

if (!existsSync(sourceDir)) {
  console.error(`copy-engine: ${sourceDir} not found; is the stockfish package installed?`)
  process.exit(1)
}

mkdirSync(targetDir, { recursive: true })
for (const file of ENGINE_FILES) {
  copyFileSync(join(sourceDir, file), join(targetDir, file))
}
console.log(`copy-engine: copied ${ENGINE_FILES.length} files to public/engine/`)
