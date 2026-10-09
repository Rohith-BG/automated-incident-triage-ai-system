import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  fetchIncidents,
  firstAlertMessage,
  isActiveStatus,
  STATUS_COLOR,
  STATUS_LABEL,
  type IncidentSummary,
  type IncidentStatus,
} from '../data/dashboard'
import { withAuthRetry } from '../lib/auth'

type LoadState = 'loading' | 'snapshot' | 'offline'

const BASE_INTERVAL_MS = 5_000
const MAX_RETRY_MS = 60_000

function relativeTime(iso: string): string {
  const minutes = Math.max(1, Math.floor((Date.now() - new Date(iso).getTime()) / 60_000))
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

function StatusDot({ status }: { status: string }) {
  const color = STATUS_COLOR[status as IncidentStatus] ?? 'var(--color-ink-3)'
  const pulse = isActiveStatus(status)
  return (
    <span
      className={`inline-block h-2 w-2 shrink-0 ${pulse ? 'animate-pulse' : ''}`}
      style={{ backgroundColor: color, borderRadius: 0 }}
      aria-hidden="true"
    />
  )
}

export default function DashboardIncidents() {
  const [state, setState] = useState<LoadState>('loading')
  const [incidents, setIncidents] = useState<IncidentSummary[]>([])
  const [error, setError] = useState<string | null>(null)
  const backoff = useRef(0)
  const loading = useRef(false)

  useEffect(() => {
    let cancelled = false

    const schedule = (delay: number) => window.setTimeout(run, delay)

    async function run() {
      if (loading.current) {
        schedule(1_000)
        return
      }
      loading.current = true
      try {
        const list = await withAuthRetry(() => fetchIncidents({ limit: 25 }))
        if (cancelled) return
        setIncidents(list.items)
        setError(null)
        setState('snapshot')
        backoff.current = 0
        loading.current = false
        timer = schedule(BASE_INTERVAL_MS)
      } catch {
        if (cancelled) return
        setError('Could not load incidents from the service.')
        setState('offline')
        backoff.current = Math.min(backoff.current + 1, MAX_RETRY_MS / 1_000)
        loading.current = false
        timer = schedule(backoff.current * 1_000)
      }
    }

    let timer = schedule(0)

    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [])

  const active = incidents.filter((i) => isActiveStatus(i.status))

  return (
    <section aria-label="Incidents" className="overflow-hidden rounded-xl border border-grid-major bg-stock">
      <div className="flex items-center justify-between border-b border-grid-major px-4 py-3">
        <div className="flex items-center gap-3">
          <h2 className="legend text-ink">Incidents</h2>
          <span
            className={`legend ${
              state === 'snapshot'
                ? 'text-ink-2'
                : state === 'offline'
                  ? 'text-tentative'
                  : 'text-ink-3'
            }`}
          >
            {state === 'snapshot'
              ? 'snapshot'
              : state === 'offline'
                ? 'offline · retrying'
                : 'loading'}
          </span>
        </div>
        <Link
          to="/incidents"
          className="legend text-ink-2 no-underline transition-colors hover:text-ink"
        >
          View all
        </Link>
      </div>

      {error ? (
        <p className="legend px-4 py-5 text-tentative">{error}</p>
      ) : state === 'loading' ? (
        <LoadingRows />
      ) : active.length === 0 ? (
        <EmptyState />
      ) : (
        <ol className="divide-y divide-grid-minor">
          {active.map((i) => (
            <Row key={i.id} incident={i} />
          ))}
        </ol>
      )}
    </section>
  )
}

function Row({ incident }: { incident: IncidentSummary }) {
  const message = firstAlertMessage(incident)
  return (
    <li className="border-b border-grid-minor last:border-b-0">
      <div className="grid grid-cols-[auto_minmax(0,10rem)_minmax(0,1fr)_auto_auto] items-center gap-x-4 gap-y-1 px-4 py-3.5 sm:grid-cols-[auto_minmax(0,10rem)_minmax(0,1fr)_auto_auto]">
        <StatusDot status={incident.status} />
        <span className="data-tight text-ink">{incident.service_id}</span>
        <span className="hidden text-[0.875rem] leading-snug text-ink-2 sm:block">
          {message ?? incident.id}
        </span>
        <span className="legend text-ink-2">{STATUS_LABEL[incident.status as IncidentStatus] ?? incident.status}</span>
        <span className="data-tight hidden text-ink-2 lg:block">{relativeTime(incident.created_at)}</span>
      </div>
    </li>
  )
}

function LoadingRows() {
  return (
    <div className="divide-y divide-grid-minor" aria-busy="true" aria-label="Loading incidents">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 px-4 py-4">
          <span className="h-2 w-2 animate-pulse bg-grid-major" />
          <span className="h-3 w-24 animate-pulse bg-stock-3" />
          <span className="h-3 flex-1 animate-pulse bg-stock-3" />
          <span className="h-3 w-20 animate-pulse bg-stock-3" />
        </div>
      ))}
    </div>
  )
}

function EmptyState() {
  return (
    <div className="flex min-h-[16rem] flex-col items-center justify-center px-6 text-center">
      <h3 className="section-type text-ink">No active incidents</h3>
      <p className="prose-measure mt-2 text-[0.9375rem] leading-relaxed text-ink-2">
        Every signal is within threshold. New alerts will appear here the moment an
        investigation starts.
      </p>
    </div>
  )
}
