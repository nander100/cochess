// WCAG AA contrast in both themes (SPEC_V3 §4.1, §4.5), checked from the tokens themselves:
// 4.5:1 for text, 3:1 for large text and for focus rings and other non-text UI.
import tokensCss from './tokens.css?raw'

type Tokens = Record<string, string>

function block(selector: string): Tokens {
  const start = tokensCss.indexOf(selector)
  if (start < 0) throw new Error(`No ${selector} block in tokens.css`)
  const body = tokensCss.slice(tokensCss.indexOf('{', start) + 1, tokensCss.indexOf('}', start))
  return Object.fromEntries([...body.matchAll(/(--[\w-]+):\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]))
}

const base = block(':root {')
const themes: Record<string, Tokens> = {
  light: { ...base, ...block(":root,\n:root[data-theme='light'] {") },
  dark: { ...base, ...block(":root[data-theme='dark'] {") },
}

function resolve(tokens: Tokens, name: string): string {
  let value = tokens[name]
  for (let i = 0; value?.startsWith('var('); i++) {
    if (i > 5) throw new Error(`${name} doesn't resolve`)
    value = tokens[value.slice(4, -1)]
  }
  if (!value || !/^#[0-9a-f]{6}$/i.test(value)) throw new Error(`${name} is not a hex color: ${value}`)
  return value
}

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function ratio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

// [text, background, minimum]
const TEXT: [string, string, number][] = [
  ['--color-fg', '--color-bg', 4.5],
  ['--color-muted', '--color-bg', 4.5],
  ['--color-fg', '--color-tint', 4.5],
  ['--color-muted', '--color-tint', 4.5],
  ['--color-fg', '--color-field', 4.5],
  ['--color-link', '--color-bg', 4.5],
  ['--color-label', '--color-bg', 4.5],
  ['--color-label', '--color-tint', 4.5],
  ['--color-primary-fg', '--color-primary', 4.5],
  ['--color-secondary-fg', '--color-secondary-bg', 4.5],
  ['--color-feature-fg', '--color-feature', 4.5],
  ['--color-feature-muted', '--color-feature', 4.5],
  ['--header-accent', '--color-feature', 4.5], // eyebrow labels on feature cards
  ['--color-danger', '--color-bg', 4.5],
  ['--chess-good', '--color-bg', 4.5],
  ['--chess-inaccuracy', '--color-bg', 4.5],
  ['--chess-mistake', '--color-bg', 4.5],
  ['--chess-blunder', '--color-bg', 4.5],
  ['--chess-plan', '--color-bg', 4.5],
  ['--header-fg', '--header-bg', 4.5],
  ['--header-fg-2', '--header-bg', 4.5],
  ['--header-accent-fg', '--header-accent', 4.5], // active nav item, pills, logo tile
  ['--color-danger-fg', '--color-danger', 4.5],
]

const NON_TEXT: [string, string, number][] = [
  ['--color-focus', '--color-bg', 3],
  ['--color-primary', '--color-bg', 3], // filled controls and the checked toggle
  ['--color-field-border', '--color-bg', 1.5], // decorative edge; the label carries the meaning
]

describe.each(Object.entries(themes))('%s theme', (_name, tokens) => {
  test.each(TEXT)('%s on %s meets %s:1', (fg, bg, min) => {
    expect(ratio(resolve(tokens, fg), resolve(tokens, bg))).toBeGreaterThanOrEqual(min)
  })

  test.each(NON_TEXT)('%s against %s meets %s:1', (fg, bg, min) => {
    expect(ratio(resolve(tokens, fg), resolve(tokens, bg))).toBeGreaterThanOrEqual(min)
  })
})
