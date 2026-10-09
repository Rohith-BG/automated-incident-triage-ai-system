/**
 * Shared hook that fetches the current user from /auth/me.
 *
 * Returns `undefined` while loading, `null` when unauthenticated, or the
 * CurrentUser object on success. Re-fetches once on mount only.
 */

import { useEffect, useState } from 'react'
import { api } from './api'
import { withAuthRetry } from './auth'

export interface CurrentUser {
  id: string
  email: string
  full_name: string
  role: string
  is_active: boolean
  created_at: string
}

export function useCurrentUser(): CurrentUser | null | undefined {
  const [user, setUser] = useState<CurrentUser | null | undefined>(undefined)

  useEffect(() => {
    let cancelled = false
    withAuthRetry(() => api.get<CurrentUser>('/auth/me'))
      .then((me) => {
        if (!cancelled) setUser(me)
      })
      .catch(() => {
        if (!cancelled) setUser(null)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return user
}
