import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { expect, test } from '@playwright/test'

// One of the owner's real games (backend/tests/fixtures/pgn/user/gameN{w|b}.txt).
const GAME_FILE = process.env.E2E_GAME ?? 'game5b.txt'
const PGN = readFileSync(
  new URL(`../../backend/tests/fixtures/pgn/user/${GAME_FILE}`, import.meta.url),
  'utf8',
)
const COLOR = GAME_FILE.replace(/\.\w+$/, '').endsWith('b') ? 'Black' : 'White'
const EVIDENCE = new URL('../test-results/m2-engine-evidence.json', import.meta.url)
// The exact results the browser posted, saved as a backend fixture so summaries can be built
// from real engine output without re-running Stockfish (backend/tests/fixtures/engine/).
const ENGINE_FIXTURE = new URL(
  `../../backend/tests/fixtures/engine/${GAME_FILE.replace(/\.\w+$/, '')}.json`,
  import.meta.url,
)

// Tier minimums from backend config: a search must reach the min depth unless it hit the cap.
const TIERS = {
  scan: { minDepth: 12, hardCapMs: 1000 },
  verify: { minDepth: 18, hardCapMs: 3000 },
}

test('analyzes a real game in the browser with the multi-threaded engine', async ({ page }) => {
  const engineLog: string[] = []
  page.on('console', (message) => {
    if (message.text().startsWith('CoChess engine:')) engineLog.push(message.text())
  })

  const posted: Record<'scan' | 'verify', unknown[]> = { scan: [], verify: [] }
  page.on('request', (request) => {
    const tier = request.url().match(/\/engine\/(scan|verify)$/)?.[1] as 'scan' | 'verify' | undefined
    if (tier && request.method() === 'POST') posted[tier] = request.postDataJSON().results
  })

  await page.goto('/')
  // The Vite dev server can reload the page once while it bundles newly added dependencies.
  await page.waitForLoadState('networkidle')
  await expect(page.getByRole('heading', { name: 'CoChess' })).toBeVisible()
  expect(await page.evaluate(() => crossOriginIsolated)).toBe(true)
  if (process.env.E2E_ACCESS_CODE) {
    await page.getByLabel('Access code').fill(process.env.E2E_ACCESS_CODE)
    await page.getByRole('button', { name: 'Continue' }).click()
  }

  await page.getByLabel(/rating/i).fill('950')
  await page.getByLabel(COLOR, { exact: true }).check()
  await page.getByLabel(/your game/i).fill(PGN)
  const started = Date.now()
  await page.getByRole('button', { name: 'Analyze' }).click()
  await expect(page.getByText('Analysis complete.')).toBeVisible({ timeout: 9 * 60_000 })
  const wallMs = Date.now() - started

  const summary = (await page.locator('.engine-stats summary').textContent()) ?? ''
  const rows = await page.locator('[data-testid=engine-results] tbody tr').evaluateAll((trs) =>
    trs.map((tr) => {
      const cells = [...tr.querySelectorAll('td')].map((td) => td.textContent ?? '')
      const [tier, position, depth, timeMs, evaluation, line] = cells
      return { tier, position, depth: Number(depth), time_ms: Number(timeMs), eval: evaluation, line }
    }),
  )

  mkdirSync(new URL('.', EVIDENCE), { recursive: true })
  const evidence = { game: GAME_FILE, color: COLOR, wall_ms: wallMs, summary, engine_log: engineLog, rows }
  writeFileSync(EVIDENCE, JSON.stringify(evidence, null, 2))
  mkdirSync(new URL('.', ENGINE_FIXTURE), { recursive: true })
  const fixture = { game: GAME_FILE, user_color: COLOR.toLowerCase(), ...posted }
  writeFileSync(ENGINE_FIXTURE, `${JSON.stringify(fixture, null, 1)}\n`)

  if (process.env.E2E_COACH === '1') {
    // Real Claude call: the synopsis arrives as validated markdown with the five sections.
    const synopsis = page.getByRole('region', { name: "Coach's synopsis" })
    await expect(synopsis.getByRole('heading', { name: 'Your turn' })).toBeVisible({ timeout: 180_000 })
    writeFileSync(new URL('../test-results/m4-synopsis.txt', import.meta.url), (await synopsis.textContent()) ?? '')

    // Chat questions, separated by "|", e.g. E2E_QUESTIONS="What if I had played 31...Kf7?"
    const questions = (process.env.E2E_QUESTIONS ?? '').split('|').filter((q) => q.trim())
    const transcript: string[] = []
    for (const [index, question] of questions.entries()) {
      await page.getByLabel('Your question').fill(question)
      await page.getByRole('button', { name: 'Send' }).click()
      const reply = page.locator('.chat-message.coach').nth(index)
      await expect(reply).toBeVisible({ timeout: 180_000 })
      transcript.push(`YOU: ${question}`, `COACH: ${(await reply.innerText()).replace(/^coach\s*/i, '')}`)
    }
    if (questions.length) {
      writeFileSync(new URL('../test-results/m5-chat.txt', import.meta.url), transcript.join('\n\n'))
    }
  }

  expect(engineLog.join()).toContain('CoChess engine: stockfish-19-lite,') // multi-threaded build
  expect(rows.some((row) => row.tier === 'verify')).toBe(true)
  for (const row of rows) {
    const tier = TIERS[row.tier as keyof typeof TIERS]
    const deepEnough = row.depth >= tier.minDepth || row.time_ms >= tier.hardCapMs
    expect(deepEnough, JSON.stringify(row)).toBe(true)
  }
})
