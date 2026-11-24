import { type Page, expect, test } from '@playwright/test'
import { logIn, newLoginLink, ownerCli } from '../login.ts'

// Google sign-in, the waitlist and Connect Google (SPEC_V4 §4) against the E2E backend's fake
// Google (backend/tests/e2e_app.py): "Continue with Google" opens a chooser where the test types
// the account; the backend checks the signed ID token as it would Google's.

const THIS_YEAR = new Date().getFullYear()
const SHOTS = new URL('../../test-results/', import.meta.url)

function account(label: string) {
  const id = `${label.toLowerCase()}-${Date.now()}`
  return { name: `${label} Player`, email: `${id}@example.com` }
}

async function chooseGoogleAccount(page: Page, who: { name: string; email: string }) {
  await page.getByRole('heading', { name: 'Choose an account' }).waitFor()
  await page.getByLabel('Name').fill(who.name)
  await page.getByLabel('Email').fill(who.email)
  await page.getByRole('button', { name: 'Continue as this account' }).click()
}

async function shot(page: Page, name: string) {
  await page.screenshot({ path: new URL(`m2-${name}.png`, SHOTS).pathname, fullPage: true })
}

test('a new player joins the waitlist with Google, is accepted, and opens the app', async ({ page }) => {
  const wendy = account('Wendy')
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Learn from every game you play.' })).toBeVisible()
  await shot(page, '1-sign-in')

  await page.getByRole('link', { name: 'Continue with Google' }).click()
  await chooseGoogleAccount(page, wendy)

  await expect(page).toHaveURL(/\/signup$/)
  await expect(page.getByRole('heading', { name: `Welcome, ${wendy.name}.` })).toBeVisible()
  await expect(page.getByLabel('What year were you born?')).toHaveValue('')
  await shot(page, '2-sign-up')
  await page.getByLabel('What year were you born?').fill(String(THIS_YEAR - 30))
  await page.getByRole('checkbox').check()
  await page.getByRole('button', { name: 'Join the waitlist' }).click()

  await expect(page.getByRole('heading', { name: `You're on the list, ${wendy.name}.` })).toBeVisible()
  await expect(page.getByText(wendy.email)).toBeVisible()
  await shot(page, '3-waitlist')

  // The owner accepts them (the CLI now, the owner dashboard in M5); a reload opens the app.
  expect(ownerCli('admit', '--user', wendy.email)).toContain('Accepted')
  await page.reload()
  await expect(page).toHaveURL(/\/profile$/) // first time in: the profile comes first
  await expect(page.getByRole('heading', { level: 1, name: wendy.name })).toBeVisible()
  await shot(page, '4-accepted')

  // Signing in again later, in a fresh browser, goes straight in.
  await page.context().clearCookies()
  await page.goto('/')
  await page.getByRole('link', { name: 'Continue with Google' }).click()
  await chooseGoogleAccount(page, wendy)
  await expect(page.getByRole('heading', { level: 1, name: wendy.name })).toBeVisible()
})

test('under 13: nothing is kept and sign-up stays closed in that browser', async ({ page }) => {
  const kid = account('Kid')
  await page.goto('/')
  await page.getByRole('link', { name: 'Continue with Google' }).click()
  await chooseGoogleAccount(page, kid)
  await page.getByLabel('What year were you born?').fill(String(THIS_YEAR - 9))
  await page.getByRole('checkbox').check()
  await page.getByRole('button', { name: 'Join the waitlist' }).click()

  await expect(page.getByRole('heading', { name: "Sorry, you can't create a CoChess account yet." })).toBeVisible()
  await shot(page, '5-too-young')
  expect(() => ownerCli('admit', '--user', kid.email)).toThrow() // no account was made

  await page.goto('/')
  await page.getByRole('link', { name: 'Continue with Google' }).click()
  await expect(page).toHaveURL(/signin=age/)
  await expect(page.getByRole('link', { name: 'Continue with Google' })).toHaveCount(0)
})

test('an invite-link player connects Google, then signs in with it', async ({ page }) => {
  const link = newLoginLink(`Invited ${Date.now()}`)
  const google = account('Invited')
  await logIn(page, link, 1300)
  await page.goto('/profile')

  const card = page.getByRole('region', { name: 'Signing in' })
  await card.getByRole('link', { name: 'Connect Google' }).click()
  await chooseGoogleAccount(page, google)

  await expect(page).toHaveURL(/\/profile\?google=connected$/)
  await expect(card.getByText('Google connected')).toBeVisible()
  await expect(card.getByText(`as ${google.email}`)).toBeVisible()
  await shot(page, '6-connected')

  await page.context().clearCookies()
  await page.goto('/')
  await page.getByRole('link', { name: 'Continue with Google' }).click()
  await chooseGoogleAccount(page, google)
  await expect(page).toHaveURL(/\/(games|onboarding|profile)/)
})
