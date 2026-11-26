import { useCallback, useEffect, useState } from 'react'
import { Link, NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router'
import type { PipelineDeps } from './analysis/pipeline'
import { createApiClient, isLoggedOut } from './api/client'
import type { EngineConfig, Profile } from './api/types'
import { type EngineHandle, StockfishEngine } from './engine/StockfishEngine'
import { GamePage } from './pages/GamePage'
import { GamesPage } from './pages/GamesPage'
import { NewGamePage } from './pages/NewGamePage'
import { OnboardingPage } from './pages/OnboardingPage'
import { BaselineReportPanel } from './onboarding/BaselineReportPanel'
import { ProfilePage } from './pages/ProfilePage'
import { RedeemPage } from './pages/RedeemPage'
import { errorText, tokenFromHash } from './pages/util'
import { useTheme } from './theme'

type Session =
  | { kind: 'loading' }
  | { kind: 'logged-out' }
  | { kind: 'error'; message: string }
  | { kind: 'in'; profile: Profile }

/** Real dependencies. The engine loads once and is reused for every game in this tab. */
function defaultDeps(): PipelineDeps {
  let engine: Promise<EngineHandle> | null = null
  return {
    api: createApiClient(),
    getEngine(config: EngineConfig) {
      engine ??= StockfishEngine.create(config).catch((error: unknown) => {
        engine = null // let the next attempt retry
        throw error
      })
      return engine
    },
  }
}

interface AppProps {
  deps?: PipelineDeps
}

export default function App({ deps }: AppProps) {
  const [pipeline] = useState(() => deps ?? defaultDeps())
  const [session, setSession] = useState<Session>({ kind: 'loading' })
  const location = useLocation()
  const navigate = useNavigate()
  // Read once: the fragment is removed from the address bar as soon as the link is used.
  const [redeemToken] = useState(() => tokenFromHash(location.hash))
  const onRedeemPage = location.pathname === '/redeem'

  const loadProfile = useCallback(() => {
    pipeline.api.me().then(
      (profile) => setSession({ kind: 'in', profile }),
      (error: unknown) =>
        setSession(isLoggedOut(error) ? { kind: 'logged-out' } : { kind: 'error', message: errorText(error) }),
    )
  }, [pipeline])

  useEffect(() => {
    if (!onRedeemPage) loadProfile()
  }, [onRedeemPage, loadProfile])

  const redeemed = useCallback(() => navigate('/games', { replace: true }), [navigate])
  const loggedOut = useCallback(() => setSession({ kind: 'logged-out' }), [])

  async function logOut() {
    await pipeline.api.logout().catch(() => undefined) // logged out either way
    setSession({ kind: 'logged-out' })
  }

  if (onRedeemPage) {
    return (
      <>
        <Header />
        <main>
          <RedeemPage api={pipeline.api} token={redeemToken} onRedeemed={redeemed} />
        </main>
      </>
    )
  }

  return (
    <>
      <Header session={session} onLogOut={() => void logOut()} />
      <main>
        {session.kind === 'loading' && <p className="coach-writing">Connecting…</p>}
        {session.kind === 'error' && (
          <p className="run-error" role="alert">
            {session.message}
          </p>
        )}
        {session.kind === 'logged-out' && (
          <p className="logged-out" role="alert">
            You're not logged in. Ask the owner for a login link, then open it in this browser.
          </p>
        )}
        {session.kind === 'in' && (
          <Routes>
            <Route
              path="/profile"
              element={
                <>
                  <ProfilePage
                    api={pipeline.api}
                    profile={session.profile}
                    onSaved={(profile) => {
                      const firstTime = !session.profile.complete
                      setSession({ kind: 'in', profile })
                      // After the first login: the onboarding assessment, which can be skipped.
                      if (firstTime && profile.complete) navigate('/onboarding')
                    }}
                    onLoggedOut={loggedOut}
                  />
                  {session.profile.complete && <BaselineReportPanel api={pipeline.api} onLoggedOut={loggedOut} />}
                </>
              }
            />
            {session.profile.complete ? (
              <>
                <Route path="/" element={<Navigate to="/games" replace />} />
                <Route path="/games" element={<GamesPage api={pipeline.api} onLoggedOut={loggedOut} />} />
                <Route path="/games/:gameId" element={<GamePage deps={pipeline} onLoggedOut={loggedOut} />} />
                <Route path="/new" element={<NewGamePage deps={pipeline} onLoggedOut={loggedOut} />} />
                <Route path="/onboarding" element={<OnboardingPage deps={pipeline} onLoggedOut={loggedOut} />} />
              </>
            ) : (
              <Route path="/" element={<Navigate to="/profile" replace />} />
            )}
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        )}
      </main>
    </>
  )
}

interface HeaderProps {
  session?: Session
  onLogOut?: () => void
}

function Header({ session, onLogOut }: HeaderProps) {
  const { theme, toggle } = useTheme()
  return (
    <header className="app-header">
      <div className="app-header-inner">
        <Link to="/" className="brand">
          <span className="brand-mark" aria-hidden="true">
            ♞&#xFE0E;
          </span>
          <h1>Tempo Labs</h1>
        </Link>
        {session?.kind === 'in' && (
          <nav aria-label="Main">
            <NavLink to="/games">My games</NavLink>
            <NavLink to="/new">Analyze a game</NavLink>
            <NavLink to="/onboarding">Assessment</NavLink>
            <NavLink to="/profile">Profile</NavLink>
          </nav>
        )}
        <div className="header-tools">
          {session?.kind === 'in' && (
            <>
              <span className="signed-in">{session.profile.name}</span>
              <button type="button" className="link-button" onClick={onLogOut}>
                Log out
              </button>
            </>
          )}
          <button
            type="button"
            className="theme-toggle"
            onClick={toggle}
            aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
          </button>
        </div>
      </div>
    </header>
  )
}

function SunIcon() {
  return (
    <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
    </svg>
  )
}
