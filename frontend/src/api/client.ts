import type {
  CreateGameRequest,
  CreateGameResponse,
  EngineConfig,
  EngineResult,
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

export interface ApiClient {
  createGame(body: CreateGameRequest): Promise<CreateGameResponse>
  engineConfig(): Promise<EngineConfig>
  submitScan(gameId: string, results: EngineResult[]): Promise<ScanResponse>
  submitVerify(gameId: string, results: EngineResult[]): Promise<VerifyResponse>
}

export function createApiClient(fetchImpl: typeof fetch = fetch.bind(globalThis)): ApiClient {
  async function request<T>(path: string, init?: RequestInit): Promise<T> {
    let response: Response
    try {
      response = await fetchImpl(path, {
        ...init,
        headers: { 'Content-Type': 'application/json', ...init?.headers },
      })
    } catch {
      throw new ApiError(0, "Couldn't reach the CoChess server. Check your connection and try again.")
    }
    const body: unknown = await response.json().catch(() => null)
    if (!response.ok) {
      throw new ApiError(response.status, errorMessage(body, response.status))
    }
    return body as T
  }

  const post = <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body) })

  return {
    createGame: (body) => post('/api/games', body),
    engineConfig: () => request('/api/engine-config'),
    submitScan: (gameId, results) => post(`/api/games/${gameId}/engine/scan`, { results }),
    submitVerify: (gameId, results) => post(`/api/games/${gameId}/engine/verify`, { results }),
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
