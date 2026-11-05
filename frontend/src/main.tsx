import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import App from './App.tsx'
import './styles/index.css'
import { applyTheme, readStoredTheme, watchSystemTheme } from './theme/theme'

const storage = (() => {
  try {
    return window.localStorage
  } catch {
    return null
  }
})()
applyTheme(readStoredTheme(storage))
watchSystemTheme(() => {
  if (readStoredTheme(storage) === 'system') applyTheme('system')
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
