import { NavLink } from 'react-router'
import type { Theme } from '../theme/theme'
import { IconButton } from './Button'
import { MoonIcon, SunIcon } from './icons'
import './Header.css'

export interface NavItem {
  to: string
  label: string
  /** Mark the link active only on an exact match. */
  end?: boolean
  /** Mark active on other paths too (e.g. "Analysis" for any /games/:id). */
  activeFor?: (pathname: string) => boolean
}

interface HeaderProps {
  nav: readonly NavItem[]
  pathname: string
  playerName: string | null
  theme: Theme
  onToggleTheme: () => void
}

/** The black bar on every page: logo, main nav, player name, theme toggle (docs/design/tokens.md). */
export function Header({ nav, pathname, playerName, theme, onToggleTheme }: HeaderProps) {
  return (
    <header className="ui-header">
      <div className="ui-header-inner">
        <NavLink to="/" className="ui-header-logo">
          <span className="ui-header-logo-tile" aria-hidden="true">
            ♞︎
          </span>
          <span className="ui-header-wordmark">CoChess</span>
        </NavLink>
        <nav aria-label="Main" className="ui-header-nav">
          {nav.map((item) => {
            const active = item.activeFor?.(pathname)
            return (
              <NavLink
                key={item.label}
                to={item.to}
                end={item.end}
                className={({ isActive }) => ((active ?? isActive) ? 'ui-nav-link active' : 'ui-nav-link')}
                aria-current={active === undefined ? undefined : active ? 'page' : false}
              >
                {item.label}
              </NavLink>
            )
          })}
        </nav>
        <div className="ui-header-end">
          {playerName && <span className="ui-header-player">{playerName}</span>}
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
