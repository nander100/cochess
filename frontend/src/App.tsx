import { useCallback, useEffect, useState } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router'
import type { PipelineDeps } from './analysis/pipeline'
import { createApiClient, isLoggedOut } from './api/client'
import type { EngineConfig, Profile } from './api/types'
import { type EngineHandle, StockfishEngine } from './engine/StockfishEngine'
import { GamePage } from './pages/GamePage'
import { GamesPage } from './pages/GamesPage'
import { LatestGamePage } from './pages/LatestGamePage'
import { OnboardingPage } from './pages/OnboardingPage'
import { ProfilePage } from './pages/ProfilePage'
import { RedeemPage } from './pages/RedeemPage'
import { errorText, tokenFromHash } from './pages/util'
import { SettingsProvider } from './settings/SettingsProvider'
import { useSettings } from './settings/settingsContext'
import { ThemeProvider } from './theme/ThemeProvider'
import { useTheme } from './theme/themeContext'
import { ErrorState, Header, type NavItem, Skeleton, ToastProvider } from './ui'

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

/** The main nav (docs/design/screens.md). "Analysis" and "Critical moments" open the latest game;
 * on a game's page, the moments view (?view=moments) highlights "Critical moments". */
function mainNav(search: string): NavItem[] {
  const moments = new URLSearchParams(search).get('view') === 'moments'
  const onGame = (path: string) => path.startsWith('/games/')
  return [
    { to: '/games', label: 'Games', activeFor: (path) => path === '/games' || path === '/new' },
    { to: '/analysis', label: 'Analysis', activeFor: (path) => path === '/analysis' || (onGame(path) && !moments) },
    { to: '/moments', label: 'Critical moments', activeFor: (path) => path === '/moments' || (onGame(path) && moments) },
    { to: '/onboarding', label: 'Assessment', activeFor: (path) => path === '/onboarding' },
    { to: '/profile', label: 'Profile', activeFor: (path) => path === '/profile' },
  ]
}

export default function App({ deps }: AppProps) {
  return (
    <ThemeProvider>
      <ToastProvider>
        <Shell deps={deps} />
      </ToastProvider>
    </ThemeProvider>
  )
}

function Shell({ deps }: AppProps) {
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

  // The invite page has its own layout (Redeem.dc.html): a brand panel instead of the header.
  if (onRedeemPage) return <RedeemPage api={pipeline.api} token={redeemToken} onRedeemed={redeemed} />

  return (
    <SettingsProvider api={pipeline.api} enabled={session.kind === 'in'}>
      <AppHeader session={session} onLogOut={() => void logOut()} />
      <main className="page">
      {session.kind === 'loading' && <Skeleton label="Connecting…" />}
      {session.kind === 'error' && <ErrorState message={session.message} onRetry={loadProfile} />}
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
            }
          />
          {session.profile.complete ? (
            <>
              <Route path="/" element={<Navigate to="/games" replace />} />
              <Route path="/games" element={<GamesPage deps={pipeline} onLoggedOut={loggedOut} />} />
              <Route path="/games/:gameId" element={<GamePage deps={pipeline} onLoggedOut={loggedOut} />} />
              <Route
                path="/analysis"
                element={<LatestGamePage api={pipeline.api} target="analysis" onLoggedOut={loggedOut} />}
              />
              <Route
                path="/moments"
                element={<LatestGamePage api={pipeline.api} target="moments" onLoggedOut={loggedOut} />}
              />
              <Route path="/new" element={<Navigate to="/games" replace />} />
              <Route path="/onboarding" element={<OnboardingPage deps={pipeline} onLoggedOut={loggedOut} />} />
            </>
          ) : (
            <Route path="/" element={<Navigate to="/profile" replace />} />
          )}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      )}
      </main>
    </SettingsProvider>
  )
}

interface AppHeaderProps {
  session?: Session
  onLogOut?: () => void
}

/** The design's black header. The nav and the player's name appear once logged in; "Log out"
 * sits with the name (the design has no place for it). */
function AppHeader({ session, onLogOut }: AppHeaderProps) {
  const { pathname, search } = useLocation()
  const { theme } = useTheme()
  const { update } = useSettings()
  const signedIn = session?.kind === 'in'
  return (
    <Header
      nav={signedIn ? mainNav(search) : []}
      pathname={pathname}
      playerName={signedIn ? session.profile.name : null}
      theme={theme}
      onToggleTheme={() => update({ theme: theme === 'dark' ? 'light' : 'dark' })}
      onLogOut={signedIn ? onLogOut : undefined}
    />
  )
}
