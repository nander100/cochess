import type { ReactNode } from 'react'
import { useTheme } from '../theme/themeContext'
import { Button } from '../ui'
import './RedeemPage.css'

/** The brand panel and a narrow card (Redeem.dc.html), for the pages shown before the app opens:
 * invite links, sign-in, sign-up, the waitlist, and the terms. */
export function AccountLayout({ children }: { children: ReactNode }) {
  return (
    <div className="redeem">
      <section className="redeem-brand" aria-hidden="true">
        <div className="redeem-logo">
          <span className="redeem-logo-tile">♞︎</span>
          <span className="redeem-wordmark">CoChess</span>
        </div>
        <div className="redeem-tiles">
          {Array.from({ length: 16 }, (_, i) => (
            <span key={i} className={(Math.floor(i / 4) + i) % 2 === 0 ? 'light' : 'dark'} />
          ))}
        </div>
        <p className="redeem-tagline">The engine finds the moves. Your coach explains them.</p>
      </section>
      <main className="redeem-main">
        <div className="redeem-card">
          {children}
          <ThemeButton />
        </div>
      </main>
    </div>
  )
}

function ThemeButton() {
  const { theme, toggle } = useTheme()
  return (
    <Button variant="outline" className="redeem-theme" onClick={toggle}>
      {theme === 'dark' ? 'Light mode' : 'Dark mode'}
    </Button>
  )
}
