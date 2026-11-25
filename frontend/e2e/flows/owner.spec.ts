import { type Browser, type Page, expect, test } from '@playwright/test'
import { logIn, newLoginLink, ownerCli } from '../login.ts'

// The owner dashboard (SPEC_V4 §10) against the E2E backend: two people join the waitlist with
// the fake Google; the owner accepts one from the waitlist tab, adds credits, revokes and restores
// access, and the audit log shows each action. Screenshots for the M5 checkpoint.

const SHOTS = new URL('../../test-results/', import.meta.url)
const THIS_YEAR = new Date().getFullYear()

async function shot(page: Page, name: string) {
  await page.screenshot({ path: new URL(`m5-${name}.png`, SHOTS).pathname, fullPage: true })
}

/** Someone joins the waitlist with Google in a browser of their own; returns that page. */
async function joinWaitlist(browser: Browser, name: string, email: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage()
  await page.goto('/')
  await page.getByRole('link', { name: 'Continue with Google' }).click()
  await page.getByLabel('Name').fill(name)
  await page.getByLabel('Email').fill(email)
  await page.getByRole('button', { name: 'Continue as this account' }).click()
  await page.getByLabel('What year were you born?').fill(String(THIS_YEAR - 30))
  await page.getByRole('checkbox').check()
  await page.getByRole('button', { name: 'Join the waitlist' }).click()
  await expect(page.getByRole('heading', { name: `You're on the list, ${name}.` })).toBeVisible()
  return page
}

async function auditSays(page: Page, text: string | RegExp) {
  await expect(page.getByRole('list', { name: 'Audit log' }).getByRole('listitem').first()).toContainText(text)
}

test('the owner accepts from the waitlist, adds credits, revokes and restores, with the audit log', async ({
  page,
  browser,
}) => {
  const stamp = Date.now()
  const wendy = { name: `Wendy ${stamp}`, email: `wendy-${stamp}@example.com` }
  const omar = { name: `Omar ${stamp}`, email: `omar-${stamp}@example.com` }
  const wendyPage = await joinWaitlist(browser, wendy.name, wendy.email)
  await joinWaitlist(browser, omar.name, omar.email)

  const owner = `Owner ${stamp}`
  await logIn(page, newLoginLink(owner), 1500)
  ownerCli('set-role', '--user', owner, '--role', 'owner')
  await page.goto('/owner')
  await expect(page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Owner' })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Money' })).toContainText('Revenue')
  await shot(page, '1-overview')

  // The waitlist, oldest first: Wendy joined before Omar.
  await page.getByRole('tab', { name: 'Waitlist' }).click()
  const waitlist = page.getByRole('table', { name: 'Waitlist' })
  const names = waitlist.getByRole('link', { name: new RegExp(`^(Wendy|Omar) ${stamp}$`) })
  await expect(names).toHaveText([wendy.name, omar.name])
  await shot(page, '2-waitlist')
  await waitlist.getByRole('button', { name: `Accept ${wendy.name}` }).click()
  await page.getByRole('dialog', { name: `Accept ${wendy.name}?` }).getByRole('button', { name: 'Accept' }).click()
  await expect(page.getByText('Accepted 1 player.')).toBeVisible()
  await expect(names).toHaveText([omar.name])

  // Wendy is in: a reload opens the app for her.
  await wendyPage.reload()
  await expect(wendyPage.getByRole('heading', { level: 1, name: wendy.name })).toBeVisible()

  // Her page: accepted, by this owner.
  await page.getByRole('tab', { name: 'Players' }).click()
  await page.getByLabel('Search').fill(wendy.email)
  await page.getByRole('button', { name: 'Search' }).click()
  await page.getByRole('table', { name: 'Players' }).getByRole('link', { name: wendy.name }).click()
  await expect(page.getByRole('heading', { level: 1, name: wendy.name })).toBeVisible()
  await auditSays(page, 'Accepted from the waitlist')
  await auditSays(page, `by ${owner}`)
  await shot(page, '3-accepted')

  // Credits, with a note.
  await page.getByRole('button', { name: 'Add or remove credits' }).click()
  const credits = page.getByRole('dialog', { name: `Credits for ${wendy.name}` })
  await credits.getByLabel('Credits').fill('25')
  await credits.getByLabel(/Note/).fill('Beta tester')
  await credits.getByRole('button', { name: 'Add 25 credits' }).click()
  await expect(page.getByRole('region', { name: 'Numbers' })).toContainText('75 credits')
  await auditSays(page, 'Added 25 credits: Beta tester')
  await expect(page.getByRole('table', { name: 'Credit ledger' })).toContainText('Added by owner')
  await shot(page, '4-credits')

  // Revoke, with a reason: Wendy is signed out.
  await page.getByRole('button', { name: 'Revoke access' }).click()
  const revoke = page.getByRole('dialog', { name: `Revoke ${wendy.name}'s access?` })
  await revoke.getByLabel(/Reason/).fill('Testing the dashboard')
  await revoke.getByRole('button', { name: 'Revoke access' }).click()
  await auditSays(page, 'Access revoked: Testing the dashboard')
  await shot(page, '5-revoked')
  await wendyPage.reload()
  await expect(wendyPage.getByRole('link', { name: 'Continue with Google' })).toBeVisible()

  // Restore.
  await page.getByRole('button', { name: 'Restore access' }).click()
  const restore = page.getByRole('dialog', { name: `Restore ${wendy.name}'s access?` })
  await restore.getByRole('button', { name: 'Restore access' }).click()
  await auditSays(page, 'Access restored')
  await expect(page.getByRole('list', { name: 'Audit log' }).getByRole('listitem')).toHaveCount(4)
  await shot(page, '6-restored')
})

test('a player who opens /owner goes home, and the API answers 404', async ({ page }) => {
  await logIn(page, newLoginLink(`Curious ${Date.now()}`), 1400)
  await page.goto('/owner')
  await expect(page).not.toHaveURL(/\/owner/)
  await expect(page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Owner' })).toHaveCount(0)

  const status = await page.evaluate(async () => (await fetch('/api/admin/overview')).status)
  expect(status).toBe(404)
})
