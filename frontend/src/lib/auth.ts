/**
 * Access-token store.
 *
 * The access token is short-lived and kept in memory only. The refresh token
 * lives in an HTTP-only cookie managed by the backend — never in localStorage
 * or sessionStorage (product Rule 17). On a 401, a silent refresh rotates the
 * pair through the cookie.
 */

import { api } from './api'

let accessToken: string | null = null

const MAX_RETRIES = 1

export function setAccessToken(token: string | null): void {
  accessToken = token
}

export function getAccessToken(): string | null {
  return accessToken
}

interface TokenResponse {
  access_token: string
}

/**
 * Attempt to rotate tokens using the HTTP-only refresh cookie. Returns true
 * when a new access token is available. Safe to call on every 401.
 */
export async function refreshAccessToken(): Promise<boolean> {
  try {
    const response = await api.post<TokenResponse>('/auth/refresh', {})
    setAccessToken(response.access_token)
    return true
  } catch {
    setAccessToken(null)
    return false
  }
}

/**
 * Wrap a fetch-producing callable with one automatic access-token refresh on
 * authentication failure. Preserves idempotency for reads and POSTs handled
 * here; callers must supply an idempotent operation.
 */
export async function withAuthRetry<T>(
  operation: () => Promise<T>,
  retried = 0,
): Promise<T> {
  try {
    return await operation()
  } catch (err) {
    const isUnauthorized =
      typeof err === 'object' &&
      err !== null &&
      'status' in err &&
      (err as { status: number }).status === 401

    if (isUnauthorized && retried < MAX_RETRIES) {
      const refreshed = await refreshAccessToken()
      if (refreshed) return withAuthRetry(operation, retried + 1)
    }
    throw err
  }
}
