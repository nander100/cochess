import { type Page, expect, test } from '@playwright/test'
import { newLoginLink } from './login.ts'
import { HUNG_KNIGHT, rapidGame } from './flows/games.ts'
import { TEST_RESULTS } from './paths.ts'

// The M1 checkpoint evidence (SPEC_V3 §12): every page in light and dark at 1280 and 1920 px.
// Run with `SCREENS=1 npx playwright test`; files land in frontend/screenshots/ (git-ignored).
const WIDTHS = [1280, 1920] as const
const THEMES = ['light', 'dark'] as const
// Outside test-results/, which Playwright clears on every run.
const OUT = `${TEST_RESULTS}/../screenshots`

/** Switch theme the way a player does (header toggle, or the invite page's button), so the app's
 * theme state and its settings controls agree with what's shown. */
async function switchTheme(page: Page, theme: 'light' | 'dark') {
  const current = await page.evaluate(() => document.documentElement.dataset.theme)
  if (current === theme) return
  const toggle = page.getByRole('button', { name: /^Switch to (light|dark) mode$|^(Light|Dark) mode$/ })
  await toggle.first().click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', theme)
}

async function shoot(page: Page, name: string) {
  await page.mouse.move(0, 0)
  for (const theme of THEMES) {
    await switchTheme(page, theme)
    for (const width of WIDTHS) {
      await page.setViewportSize({ width, height: 1000 })
      await page.waitForTimeout(150) // layout and transitions settle
      await page.screenshot({ path: `${OUT}/${name}-${theme}-${width}.png`, fullPage: true })
    }
  }
}

const nav = (page: Page, name: string) =>
  page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name }).click()

test('every page, light and dark, 1280 and 1920', async ({ page, browser }) => {
  // Redeem: checking (the request is held), accepted, then used/expired in another tab.
  const link = newLoginLink(`Screens ${Date.now()}`)
  const url = new URL(link)
  let release: () => void = () => {}
  await page.route('**/api/auth/redeem', async (route) => {
    await new Promise<void>((resolve) => {
      release = resolve
    })
    await route.continue()
  })
  await page.goto(`${url.pathname}${url.hash}`)
  await expect(page.getByRole('progressbar')).toBeVisible()
  await shoot(page, 'redeem-checking')
  release()
  await expect(page.getByText('Invite accepted')).toBeVisible()
  await page.unroute('**/api/auth/redeem')
  await shoot(page, 'redeem-accepted')

  const other = await browser.newPage()
  await other.goto(`${url.pathname}${url.hash}`)
  await expect(other.getByRole('heading', { name: "This invite link can't be used." })).toBeVisible()
  await shoot(other, 'redeem-invalid')
  await other.close()

  await page.getByRole('link', { name: 'Set up my profile' }).click()
  await page.getByLabel(/rating/i).waitFor()
  await shoot(page, 'profile-first-time')

  // Onboarding with a few games checked.
  await page.getByLabel(/rating/i).fill('1200')
  await page.getByLabel('Rapid', { exact: true }).check()
  await page.getByRole('button', { name: /^Save/ }).click()
  await page.getByRole('heading', { name: 'Twelve games, one honest picture of your play.' }).waitFor()
  const games = [rapidGame(0, 'white', '1-0'), rapidGame(1, 'black', '0-1'), rapidGame(2, 'white', '0-1')]
  await page.getByLabel(/Paste one or more games/).fill(games.join('\n\n'))
  await page.getByRole('button', { name: 'Check games' }).click()
  await page.locator('table').waitFor()
  await shoot(page, 'onboarding-checked')

  // Games and Analysis with no games yet.
  await nav(page, 'Games')
  await page.waitForLoadState('networkidle')
  await shoot(page, 'games-empty')
  await nav(page, 'Analysis')
  await page.waitForLoadState('networkidle')
  await shoot(page, 'analysis-empty')

  // A game: the analysis board, the moments view, the games list, the profile, the assessment.
  await nav(page, 'Games')
  await page.getByLabel('I played White').check()
  await page.getByLabel(/your game/i).fill(HUNG_KNIGHT)
  await page.getByRole('button', { name: /^Analyze/ }).click()
  await expect(page).toHaveURL(/\/games\/[0-9a-f-]+$/, { timeout: 60_000 })
  await page.locator('cg-board').waitFor()
  await page.waitForLoadState('networkidle')
  await shoot(page, 'analysis')

  await nav(page, 'Critical moments')
  await page.waitForLoadState('networkidle')
  await shoot(page, 'moment')

  await nav(page, 'Games')
  await page.locator('table').waitFor()
  await shoot(page, 'games')

  await nav(page, 'Profile')
  await page.waitForLoadState('networkidle')
  await shoot(page, 'profile')

  await nav(page, 'Assessment')
  await page.waitForLoadState('networkidle')
  await shoot(page, 'onboarding')

  await page.getByRole('button', { name: 'Log out' }).click()
  await shoot(page, 'logged-out')
})
