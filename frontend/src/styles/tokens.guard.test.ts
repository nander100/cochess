// Every color and font comes from the design tokens (CLAUDE.md conventions, docs/design/tokens.md).
// This test fails if a stylesheet or component outside tokens.css uses a raw color or font stack.

const sources = import.meta.glob(['../**/*.{css,ts,tsx}', '!../**/*.test.{ts,tsx}', '!../test/**'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

const ALLOWED = new Set(['./tokens.css', './fonts.css'])
const RAW_COLOR = /#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(/
const RAW_FONT = /font-family:\s*(?!var\(|inherit)/

function offenders(pattern: RegExp): string[] {
  return Object.entries(sources)
    .filter(([path]) => !ALLOWED.has(path))
    .flatMap(([path, text]) =>
      text
        .split('\n')
        .map((line, i) => ({ line, at: `${path}:${i + 1}` }))
        .filter(({ line }) => pattern.test(line))
        .map(({ at, line }) => `${at}  ${line.trim()}`),
    )
}

test('the sources were found', () => {
  expect(Object.keys(sources).length).toBeGreaterThan(20)
})

test('no raw colors outside the tokens', () => {
  expect(offenders(RAW_COLOR)).toEqual([])
})

test('no raw font stacks outside the tokens', () => {
  expect(offenders(RAW_FONT)).toEqual([])
})
