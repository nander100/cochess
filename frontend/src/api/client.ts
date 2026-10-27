import { type CoachEvent, readCoachEvents } from './sse'
import type {
  CreateGameRequest,
  CreateGameResponse,
  EngineConfig,
  EngineResult,
  GameDetail,
  GameListItem,
  Profile,
  ProfileUpdate,
  ScanResponse,
  VerifyResponse,
} from './types'

/** An API call failed. `message` is suitable to show the user. */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

/** The request needs a login: no session, or it expired (the server answered 401). */
export function isLoggedOut(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401
}

export interface ApiClient {
  /** Use a one-time login link's token; the server sets the session cookie. */
  redeem(token: string): Promise<void>
  logout(): Promise<void>
  me(): Promise<Profile>
  updateMe(update: ProfileUpdate): Promise<Profile>
  createGame(body: CreateGameRequest): Promise<CreateGameResponse>
  listGames(): Promise<GameListItem[]>
  getGame(gameId: string): Promise<GameDetail>
  engineConfig(): Promise<EngineConfig>
  submitScan(gameId: string, results: EngineResult[]): Promise<ScanResponse>
  submitVerify(gameId: string, results: EngineResult[]): Promise<VerifyResponse>
  /** Resolves when the stream ends; coach failures arrive as an `error` event. */
  streamSynopsis(gameId: string, onEvent: (event: CoachEvent) => void): Promise<void>
  sendChat(gameId: string, message: string, onEvent: (event: CoachEvent) => void): Promise<void>
  /** Answer a coach `engine_request` with deep-dive results; the answer streams back. */
  submitEngineResult(
    gameId: string,
    requestId: string,
    results: EngineResult[],
    onEvent: (event: CoachEvent) => void,
  ): Promise<void>
}

export function createApiClient(fetchImpl: typeof fetch = fetch.bind(globalThis)): ApiClient {
  /** Fetch, turning network failures and non-2xx responses into ApiErrors. The session is an
   * httpOnly cookie, sent by the browser on same-origin requests. */
  async function send(path: string, init?: RequestInit): Promise<Response> {
    let response: Response
    try {
      response = await fetchImpl(path, {
        ...init,
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', ...init?.headers },
      })
    } catch {
      throw new ApiError(0, "Couldn't reach the CoChess server. Check your connection and try again.")
    }
    if (!response.ok) {
      const body: unknown = await response.json().catch(() => null)
      throw new ApiError(response.status, errorMessage(body, response.status))
    }
    return response
  }

  async function request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await send(path, init)
    return (await response.json()) as T
  }

  async function stream(
    path: string,
    body: unknown,
    onEvent: (event: CoachEvent) => void,
  ): Promise<void> {
    const init: RequestInit = { method: 'POST' }
    if (body !== null) init.body = JSON.stringify(body)
    const response = await send(path, init)
    if (!response.body) throw new ApiError(response.status, 'The coach sent an empty response.')
    await readCoachEvents(response.body, onEvent)
  }

  const post = <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body) })

  return {
    redeem: async (token) => {
      await send('/api/auth/redeem', { method: 'POST', body: JSON.stringify({ token }) })
    },
    logout: async () => {
      await send('/api/auth/logout', { method: 'POST' })
    },
    me: () => request('/api/me'),
    updateMe: (update) => request('/api/me', { method: 'PATCH', body: JSON.stringify(update) }),
    createGame: (body) => post('/api/games', body),
    listGames: () => request('/api/games'),
    getGame: (gameId) => request(`/api/games/${encodeURIComponent(gameId)}`),
    engineConfig: () => request('/api/engine-config'),
    submitScan: (gameId, results) => post(`/api/games/${gameId}/engine/scan`, { results }),
    submitVerify: (gameId, results) => post(`/api/games/${gameId}/engine/verify`, { results }),
    streamSynopsis: (gameId, onEvent) => stream(`/api/games/${gameId}/synopsis`, null, onEvent),
    sendChat: (gameId, message, onEvent) =>
      stream(`/api/games/${gameId}/chat`, { message }, onEvent),
    submitEngineResult: (gameId, requestId, results, onEvent) =>
      stream(`/api/games/${gameId}/chat/engine_result`, { request_id: requestId, results }, onEvent),
  }
}

/** FastAPI errors: `detail` is a string, a `{message}` object (PGN errors), or a list (validation). */
function errorMessage(body: unknown, status: number): string {
  const detail = isRecord(body) ? body.detail : undefined
  if (typeof detail === 'string') return detail
  if (isRecord(detail) && typeof detail.message === 'string') return detail.message
  if (Array.isArray(detail) && isRecord(detail[0]) && typeof detail[0].msg === 'string') {
    return detail[0].msg
  }
  return `Something went wrong (error ${status}). Please try again.`
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}
