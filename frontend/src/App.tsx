import { Suspense, lazy, useCallback, useEffect, useState } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router'
import { AnalysisQueueContext } from './analysis/analysisQueueContext'
import { AnalysisQueue, browserLock, browserStorage } from './analysis/backgroundQueue'
import type { PipelineDeps } from './analysis/pipeline'
import { createApiClient, isLoggedOut } from './api/client'
import { QueueStatus } from './components/QueueStatus'
import type { EngineConfig, Profile } from './api/types'
import { poolSize } from './engine/pool'
import { type EngineHandle, StockfishEngine } from './engine/StockfishEngine'
import { GamesPage } from './pages/GamesPage'
import { LatestGamePage } from './pages/LatestGamePage'
import { AccountStatusPage, LegalPage, SignInPage } from './pages/AccountPages'
import { RedeemPage } from './pages/RedeemPage'
import { SignupPage } from './pages/SignupPage'
import { errorText, tokenFromHash } from './pages/util'
import { SettingsProvider } from './settings/SettingsProvider'
import { ShortcutHelp } from './shortcuts/ShortcutHelp'
import { useShortcuts } from './shortcuts/useShortcuts'
import { useSettings } from './settings/settingsContext'
import { ThemeProvider } from './theme/ThemeProvider'
import { useTheme } from './theme/themeContext'
import { ErrorState, Header, type NavItem, Skeleton, ToastProvider } from './ui'

// Loaded when first opened: the board, chessground, chess.js and the coach panel stay out of the
// first download (the Games page is home and loads with the app).
const GamePage = lazy(() => import('./pages/GamePage').then((m) => ({ default: m.GamePage })))
const OnboardingPage = lazy(() => import('./pages/OnboardingPage').then((m) => ({ default: m.OnboardingPage })))
const ProfilePage = lazy(() => import('./pages/ProfilePage').then((m) => ({ default: m.ProfilePage })))
const BillingReturnPage = lazy(() =>
  import('./pages/BillingReturnPage').then((m) => ({ default: m.BillingReturnPage })),
)
// The owner dashboard (SPEC_V4 §10): its own chunk, only ever loaded by an owner.
const OwnerArea = lazy(() => import('./owner/OwnerPage').then((m) => ({ default: m.OwnerArea })))

type Session =
  | { kind: 'loading' }
  | { kind: 'logged-out' }
  | { kind: 'error'; message: string }
  | { kind: 'in'; profile: Profile }

/** Real dependencies. The engine loads once and is reused for every game in this tab. */
function defaultDeps(): PipelineDeps {
  let engine: Promise<EngineHandle> | null = null
  let pool: Promise<EngineHandle[]> | null = null
  return {
    api: createApiClient(),
    getEngine(config: EngineConfig) {
      engine ??= StockfishEngine.create(config).catch((error: unknown) => {
        engine = null // let the next attempt retry
        throw error
      })
      return engine
    },
    // Scan and verify on several single-threaded engines (SPEC_V4 §8.2), made once per tab.
    getPool(config: EngineConfig) {
      const size = poolSize(config.pool_size, navigator.hardwareConcurrency || 2)
      if (size < 2) return Promise.resolve(null)
      pool ??= Promise.all(
        Array.from({ length: size }, () => StockfishEngine.create(config, { pooled: true })),
      ).then(
        (engines) => {
          console.info(`CoChess engine pool: ${engines[0].build}, ${engines.length} engines`)
          return engines
        },
        (error: unknown) => {
          pool = null
          throw error
        },
      )
      return pool
    },
  }
}

interface AppProps {
  deps?: PipelineDeps
}

/** The main nav (docs/design/screens.md). "Analysis" and "Critical moments" open the latest game;
 * on a game's page, the moments view (?view=moments) highlights "Critical moments". */
function mainNav(search: string, owner: boolean): NavItem[] {
  const moments = new URLSearchParams(search).get('view') === 'moments'
  const onGame = (path: string) => path.startsWith('/games/')
  const ownerLink: NavItem[] = owner
    ? [{ to: '/owner', label: 'Owner', activeFor: (path) => path === '/owner' || path.startsWith('/owner/') }]
    : []
  return [
    { to: '/games', label: 'Games', activeFor: (path) => path === '/games' || path === '/new' },
    { to: '/analysis', label: 'Analysis', activeFor: (path) => path === '/analysis' || (onGame(path) && !moments) },
    { to: '/moments', label: 'Critical moments', activeFor: (path) => path === '/moments' || (onGame(path) && moments) },
    { to: '/onboarding', label: 'Assessment', activeFor: (path) => path === '/onboarding' },
    { to: '/profile', label: 'Profile', activeFor: (path) => path === '/profile' },
    ...ownerLink,
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
  // Imported games analyzed in the background, on every page (SPEC_V4 §8.2); one per tab.
  const [queue] = useState(() => new AnalysisQueue(pipeline, browserStorage(), browserLock()))
  const [session, setSession] = useState<Session>({ kind: 'loading' })
  const location = useLocation()
  const navigate = useNavigate()
  // Read once: the fragment is removed from the address bar as soon as the link is used.
  const [redeemToken] = useState(() => tokenFromHash(location.hash))
  const onRedeemPage = location.pathname === '/redeem'
  // Pages with their own layout that don't need a session (SPEC_V4 §4.2, §11).
  const standalone = ['/redeem', '/signup', '/terms', '/privacy'].includes(location.pathname)

  const loadProfile = useCallback(() => {
    pipeline.api.me().then(
      (profile) => setSession({ kind: 'in', profile }),
      (error: unknown) =>
        setSession(isLoggedOut(error) ? { kind: 'logged-out' } : { kind: 'error', message: errorText(error) }),
    )
  }, [pipeline])

  useEffect(() => {
    if (!standalone) loadProfile()
  }, [standalone, loadProfile])

  const redeemed = useCallback(() => navigate('/games', { replace: true }), [navigate])
  const loggedOut = useCallback(() => setSession({ kind: 'logged-out' }), [])
  const joined = useCallback(() => navigate('/', { replace: true }), [navigate])
  const accepted = useCallback(
    (profile: Profile) => {
      setSession({ kind: 'in', profile })
      navigate('/', { replace: true })
    },
    [navigate],
  )

  const active = session.kind === 'in' && session.profile.status === 'active'
  useEffect(() => {
    if (active) queue.resume() // games left waiting by a reload or an expired session
  }, [active, queue])

  async function logOut() {
    queue.clear() // the next player in this browser doesn't inherit the queue
    await pipeline.api.logout().catch(() => undefined) // logged out either way
    setSession({ kind: 'logged-out' })
  }

  // The invite page has its own layout (Redeem.dc.html): a brand panel instead of the header.
  if (onRedeemPage) return <RedeemPage api={pipeline.api} token={redeemToken} onRedeemed={redeemed} />
  if (location.pathname === '/signup') return <SignupPage api={pipeline.api} onJoined={joined} />
  if (location.pathname === '/terms' || location.pathname === '/privacy') {
    return <LegalPage kind={location.pathname === '/terms' ? 'terms' : 'privacy'} />
  }
  if (session.kind === 'logged-out') {
    return <SignInPage reason={new URLSearchParams(location.search).get('signin')} />
  }
  if (session.kind === 'in' && session.profile.status !== 'active') {
    return (
      <AccountStatusPage
        api={pipeline.api}
        profile={session.profile}
        onActive={accepted}
        onLogOut={() => void logOut()}
      />
    )
  }

  return (
    <AnalysisQueueContext.Provider value={queue}>
    <SettingsProvider api={pipeline.api} enabled={session.kind === 'in'}>
      <AppHeader session={session} onLogOut={() => void logOut()} />
      {active && <QueueStatus />}
      <main className="page">
      {session.kind === 'loading' && <Skeleton label="Connecting…" />}
      {session.kind === 'error' && <ErrorState message={session.message} onRetry={loadProfile} />}
      {session.kind === 'in' && (
        <Suspense fallback={<Skeleton lines={4} label="Loading…" />}>
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
          <Route path="/billing/return" element={<BillingReturnPage api={pipeline.api} />} />
          {session.profile.role === 'owner' && (
            <Route path="/owner/*" element={<OwnerArea api={pipeline.api.owner} />} />
          )}
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
        </Suspense>
      )}
      </main>
    </SettingsProvider>
    </AnalysisQueueContext.Provider>
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
  const [help, setHelp] = useState(false)
  // Shortcuts that work on every page (SPEC_V3 §4.4); the game page adds the board's own.
  useShortcuts({
    help: signedIn ? () => setHelp(true) : null,
    focusChat: () => document.querySelector<HTMLElement>('[data-shortcut="chat"]')?.focus(),
  })
  return (
    <>
      <Header
      nav={signedIn ? mainNav(search, session.profile.role === 'owner') : []}
      pathname={pathname}
      playerName={signedIn ? session.profile.name : null}
      theme={theme}
      onToggleTheme={() => update({ theme: theme === 'dark' ? 'light' : 'dark' })}
      onLogOut={signedIn ? onLogOut : undefined}
      onShowShortcuts={signedIn ? () => setHelp(true) : undefined}
      />
      <ShortcutHelp open={help} onClose={() => setHelp(false)} />
    </>
  )
}
