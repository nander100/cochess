import { readFile } from 'node:fs/promises'
import { expect, test } from '@playwright/test'
import { playMove } from '../board.ts'
import { logInWithProfile, newLoginLink } from '../login.ts'
import { HUNG_KNIGHT } from './games.ts'

// SPEC_V3 §5: a line played on the board saves itself, is there after a reload, and the exported
// PGN carries it with the evaluations and the player's mistakes marked.
test('a variation is saved, survives a reload, and is in the exported PGN', async ({ page }) => {
  await logInWithProfile(page, newLoginLink(`Variations ${Date.now()}`), 1200)
  await page.getByLabel('I played White').check()
  await page.getByLabel(/your game/i).fill(HUNG_KNIGHT)
  await page.getByRole('button', { name: 'Analyze' }).click()
  await expect(page).toHaveURL(/\/games\/[0-9a-f-]+$/, { timeout: 60_000 })
  await expect(page.getByRole('region', { name: 'Unfinished analysis' })).toBeHidden({ timeout: 60_000 })

  await page.getByRole('button', { name: /^Moves/ }).click()
  const moves = page.getByLabel('Moves')
  await moves.getByRole('button', { name: '1... e5' }).click()
  const saved = page.waitForResponse((r) => r.url().endsWith('/variations') && r.request().method() === 'PUT')
  await playMove(page, 'f1c4', 'white')
  expect((await saved).status()).toBe(200)

  await page.reload()
  await page.getByRole('button', { name: /^Moves/ }).click()
  const variation = page.getByLabel('Moves').getByRole('group', { name: 'Variation' })
  await expect(variation.getByRole('button', { name: '2. Bc4' })).toBeVisible()

  const download = page.waitForEvent('download')
  await page.getByRole('region', { name: 'Game options' }).getByRole('button', { name: 'Export PGN' }).click()
  const file = await download
  expect(file.suggestedFilename()).toBe('Player-vs-Opponent-2026.10.01.pgn')
  const pgn = await readFile((await file.path()) ?? '', 'utf8')
  expect(pgn).toContain('[Event "E2E"]')
  expect(pgn).toContain('( 2. Bc4 )')
  expect(pgn).toContain('[%eval')
  expect(pgn).toMatch(/3\. Ng5 \$4/) // the hung knight, marked ??
})

// SPEC_V3 done-condition: exported PGNs re-import cleanly. Another player pastes the exported
// file (variations, NAGs, evals and comments included) and gets the same game.
test('an exported PGN re-imports cleanly as a new game', async ({ page, browser }) => {
  await logInWithProfile(page, newLoginLink(`Export ${Date.now()}`), 1200)
  await page.getByLabel('I played White').check()
  await page.getByLabel(/your game/i).fill(HUNG_KNIGHT)
  await page.getByRole('button', { name: 'Analyze' }).click()
  await expect(page).toHaveURL(/\/games\/[0-9a-f-]+$/, { timeout: 60_000 })
  await expect(page.getByRole('region', { name: 'Unfinished analysis' })).toBeHidden({ timeout: 60_000 })
  const original = await (await page.request.get(`/api/games/${page.url().split('/').at(-1)}`)).json()
  const download = page.waitForEvent('download')
  await page.getByRole('region', { name: 'Game options' }).getByRole('button', { name: 'Export PGN' }).click()
  const exported = await readFile((await (await download).path()) ?? '', 'utf8')

  const other = await (await browser.newContext()).newPage()
  await logInWithProfile(other, newLoginLink(`Re-import ${Date.now()}`), 1200)
  await other.getByLabel('I played White').check()
  await other.getByLabel(/your game/i).fill(exported)
  await other.getByRole('button', { name: 'Analyze' }).click()

  await expect(other).toHaveURL(/\/games\/[0-9a-f-]+$/, { timeout: 60_000 })
  const copy = await (await other.request.get(`/api/games/${other.url().split('/').at(-1)}`)).json()
  const sans = (game: { moves: { san: string }[] }) => game.moves.map((m) => m.san)
  expect(sans(copy)).toEqual(sans(original))
  expect(copy.final_fen).toBe(original.final_fen)
})
