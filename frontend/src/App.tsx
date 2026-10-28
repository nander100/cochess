import { useCallback, useEffect, useState } from 'react'
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router'
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
      <main>
        <Header />
        <RedeemPage api={pipeline.api} token={redeemToken} onRedeemed={redeemed} />
      </main>
    )
  }

  return (
    <main>
      <Header session={session} onLogOut={() => void logOut()} />
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
  )
}

interface HeaderProps {
  session?: Session
  onLogOut?: () => void
}

function Header({ session, onLogOut }: HeaderProps) {
  return (
    <header>
      <h1>CoChess</h1>
      <p className="tagline">Paste a game. The engine finds what happened; your coach explains it.</p>
      {session?.kind === 'in' && (
        <nav aria-label="Main">
          <span className="signed-in">{session.profile.name}</span>
          <Link to="/games">My games</Link>
          <Link to="/new">Analyze a game</Link>
          <Link to="/onboarding">Assessment</Link>
          <Link to="/profile">Profile</Link>
          <button type="button" className="link-button" onClick={onLogOut}>
            Log out
          </button>
        </nav>
      )}
    </header>
  )
}
