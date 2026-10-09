/**
 * Typed WebSocket hook for real-time incident investigation progress and
 * notifications.
 *
 * The backend authenticates WebSocket connections via a `token` query param
 * (JWT access token). Reconnects with backoff and surfaces a connection state
 * so the UI can show a disconnection banner.
 */

import { useEffect, useRef, useState } from 'react'
import { getAccessToken } from './auth'

export interface ProgressEvent {
  event_type: string
  message?: string
  details?: Record<string, unknown>
}

export interface NotificationEvent {
  notification?: unknown
}

type SockState = 'connecting' | 'open' | 'closed'

const MAX_BACKOFF_MS = 30_000
const BASE_BACKOFF_MS = 1_000

function wsUrl(pathWithLeadingSlash: string): string {
  const base = (import.meta.env.VITE_API_URL as string | undefined) ?? ''
  if (base) {
    // Explicit API URL set — swap http(s) scheme for ws(s)
    return base.replace(/^http/, 'ws') + pathWithLeadingSlash
  }
  // Dev proxy: same host, derive ws/wss from current page protocol
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${window.location.host}${pathWithLeadingSlash}`
}

function useWebSocket(
  path: string | null,
  onMessage: (data: unknown, event: ProgressEvent) => void,
): SockState {
  const [state, setState] = useState<SockState>('connecting')
  const onMessageRef = useRef(onMessage)
  onMessageRef.current = onMessage

  useEffect(() => {
    if (!path) {
      setState('closed')
      return
    }

    let socket: WebSocket | null = null
    let closedByHook = false
    let retries = 0
    let timeout = 0

    const connect = () => {
      const token = getAccessToken()
      const separator = path.includes('?') ? '&' : '?'
      const url = `${wsUrl(path)}${separator}token=${encodeURIComponent(token ?? '')}`
      setState('connecting')
      socket = new WebSocket(url)

      socket.onopen = () => {
        retries = 0
        setState('open')
      }

      socket.onmessage = (event: MessageEvent<string>) => {
        if (event.data === 'pong') return
        try {
          const parsed = JSON.parse(event.data) as ProgressEvent
          if (parsed && parsed.event_type) {
            onMessageRef.current(parsed, parsed)
          }
        } catch {
          /* ignore non-JSON / keep-alive frames */
        }
      }

      socket.onclose = () => {
        if (closedByHook) {
          setState('closed')
          return
        }
        setState('closed')
        const delay = Math.min(BASE_BACKOFF_MS * 2 ** retries, MAX_BACKOFF_MS)
        retries += 1
        timeout = window.setTimeout(connect, delay)
      }

      socket.onerror = () => {
        socket?.close()
      }
    }

    connect()

    return () => {
      closedByHook = true
      window.clearTimeout(timeout)
      socket?.close()
    }
  }, [path])

  return state
}

/**
 * Subscribe to investigation progress for a single incident.
 * Pass `incidentId = null` to disable the connection.
 */
export function useIncidentStream(
  incidentId: string | null,
  onProgress: (event: ProgressEvent) => void,
): SockState {
  return useWebSocket(
    incidentId ? `/ws/incidents/${incidentId}` : null,
    (_data, event) => onProgress(event),
  )
}

/**
 * Subscribe to the notifications channel broadcast to all clients.
 */
export function useNotificationStream(
  enabled: boolean,
  onEvent: (event: NotificationEvent) => void,
): SockState {
  return useWebSocket(enabled ? '/ws/notifications' : null, (data) => onEvent(data as NotificationEvent))
}
