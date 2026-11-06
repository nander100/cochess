// Apply the saved theme before first paint (src/theme/theme.ts has the same rules). A file, not
// an inline script, so the production Content-Security-Policy (script-src 'self') allows it.
try {
  var t = localStorage.getItem('cochess-theme')
  if (t === 'system') t = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  document.documentElement.dataset.theme = t === 'dark' ? 'dark' : 'light'
} catch {
  document.documentElement.dataset.theme = 'light'
}
