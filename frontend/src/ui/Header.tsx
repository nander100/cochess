import { Link } from 'react-router'
import type { Theme } from '../theme/theme'
import { IconButton } from './Button'
import { MoonIcon, SunIcon } from './icons'
import './Header.css'

export interface NavItem {
  to: string
  label: string
  /** When the link is the current page; by default, an exact path match. Lets "Analysis" stay
   * active on any /games/:id. */
  activeFor?: (pathname: string) => boolean
}

interface HeaderProps {
  nav: readonly NavItem[]
  pathname: string
  playerName: string | null
  theme: Theme
  onToggleTheme: () => void
  /** Shown next to the player's name when logged in. */
  onLogOut?: () => void
}

/** The black bar on every page: logo, main nav, player name, theme toggle (docs/design/tokens.md). */
export function Header({ nav, pathname, playerName, theme, onToggleTheme, onLogOut }: HeaderProps) {
  return (
    <header className="ui-header">
      <div className="ui-header-inner">
        <Link to="/" className="ui-header-logo">
          <span className="ui-header-logo-tile" aria-hidden="true">
            ♞︎
          </span>
          <span className="ui-header-wordmark">CoChess</span>
        </Link>
        <nav aria-label="Main" className="ui-header-nav">
          {nav.map((item) => {
            const active = item.activeFor ? item.activeFor(pathname) : pathname === item.to
            return (
              <Link
                key={item.label}
                to={item.to}
                className={active ? 'ui-nav-link active' : 'ui-nav-link'}
                aria-current={active ? 'page' : undefined}
              >
                {item.label}
              </Link>
            )
          })}
        </nav>
        <div className="ui-header-end">
          {playerName && <span className="ui-header-player">{playerName}</span>}
          {onLogOut && (
            <button type="button" className="ui-header-logout" onClick={onLogOut}>
              Log out
            </button>
          )}
          <IconButton
            variant="header"
            label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            icon={theme === 'dark' ? <SunIcon /> : <MoonIcon />}
            onClick={onToggleTheme}
          />
        </div>
      </div>
    </header>
  )
}
