// The v1 shared access code (SPEC §4.2), entered once per browser session (SPEC §3).
import { ApiError } from './client'

const KEY = 'cochess-access-code'

// sessionStorage can throw (privacy modes, blocked storage); the gate then just asks again.
export function readAccessCode(): string | null {
  try {
    return sessionStorage.getItem(KEY)
  } catch {
    return null
  }
}

export function saveAccessCode(code: string): void {
  try {
    sessionStorage.setItem(KEY, code)
  } catch {
    // keep working for this page load; the code just won't survive a reload
  }
}

export function clearAccessCode(): void {
  try {
    sessionStorage.removeItem(KEY)
  } catch {
    // nothing stored
  }
}

export function isAccessDenied(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401
}
