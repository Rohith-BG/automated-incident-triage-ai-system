import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import BoardMasthead from '../components/BoardMasthead'
import RegisterRow from '../components/RegisterRow'
import {
  fetchIncidents,
  fetchRegisteredServices,
  type IncidentSummary,
  type IncidentStatus,
} from '../data/dashboard'
import { withAuthRetry } from '../lib/auth'

type LoadState = 'loading' | 'snapshot' | 'offline'

const STATUS_FILTERS: { value: IncidentStatus | ''; label: string }[] = [
  { value: '', label: 'All' },
  { value: 'investigating', label: 'Investigating' },
  { value: 'root_cause_identified', label: 'Root cause found' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
]

export default function Incidents() {
  const [searchParams, setSearchParams] = useSearchParams()
  const status = (searchParams.get('status') as IncidentStatus | null) ?? ''
  const service = searchParams.get('service') ?? ''

  const [state, setState] = useState<LoadState>('loading')
  const [rows, setRows] = useState<IncidentSummary[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [registryServices, setRegistryServices] = useState<
    { id: string }[]
  >([])

  const cursorStack = useRef<string[]>([])
  const cursorAt = useRef<string | null>(null)
  const timing = useRef<number | null>(null)
  const pending = useRef(false)

  useEffect(() => {
    let cancelled = false
    withAuthRetry(() => fetchRegisteredServices())
      .then((s) => {
        if (!cancelled) {
          setRegistryServices(
            s
              .filter((entry) => entry.is_active)
              .map((entry) => ({ id: entry.service_id })),
          )
        }
      })
      .catch(() => {
        /* Configured services require a session; only "All" is shown. */
      })
    return () => {
      cancelled = true
    }
  }, [])

  const services = useMemo(
    () =>
      registryServices.map((entry) => ({ id: entry.id })),
    [registryServices],
  )

  async function load(cursor: string | null) {
    if (pending.current) return
    pending.current = true
    setState(cursor === null ? 'loading' : 'snapshot')
    try {
      const list = await withAuthRetry(() =>
        fetchIncidents({ limit: 50, cursor: cursor ?? undefined, status: status || undefined, service_id: service || undefined }),
      )
      setRows(list.items)
      setNextCursor(list.next_cursor)
      setHasMore(list.has_more)
      setError(null)
      cursorAt.current = cursor
      setState('snapshot')
      pending.current = false
      if (timing.current) {
        window.clearTimeout(timing.current)
        timing.current = null
      }
    } catch (err) {
      setError('Could not read the incident register.')
      setState('offline')
      pending.current = false
      if (timing.current) window.clearTimeout(timing.current)
      timing.current = window.setTimeout(() => {
        load(cursor)
      }, 30_000)
    }
  }

  useEffect(() => {
    cursorStack.current = []
    cursorAt.current = null
    load(null)
    return () => {
      if (timing.current) window.clearTimeout(timing.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, service])

  function setFilter(next: { status?: string; service?: string }) {
    const params = new URLSearchParams(searchParams)
    if (next.status !== undefined) {
      if (next.status) params.set('status', next.status)
      else params.delete('status')
    }
    if (next.service !== undefined) {
      if (next.service) params.set('service', next.service)
      else params.delete('service')
    }
    setSearchParams(params)
  }

  function next() {
    if (!nextCursor) return
    cursorStack.current.push(cursorAt.current ?? '')
    load(nextCursor)
  }

  function previous() {
    const cursor = cursorStack.current.pop()
    load(cursor || null)
  }

  const activeCount = rows.filter((r) => r.status === 'investigating' || r.status === 'root_cause_identified').length

  return (
    <div className="min-h-dvh">
      <BoardMasthead />

      <main className="mx-auto w-full max-w-[1400px] px-5 py-10 sm:px-8 lg:px-12">
        <header className="mb-8">
          <h1 className="verdict-type text-[clamp(2rem,4.5vw,3.25rem)]">Incidents</h1>
          <p className="prose-measure mt-3 text-[1.0625rem] leading-[1.6] text-ink-2">
            Every investigation on record. Each row is one alert turned into a
            pipeline run; open it for the evidence and the root-cause report.
          </p>
        </header>

        <div className="mb-4 flex flex-wrap items-center gap-x-8 gap-y-3">
          <div
            role="tablist"
            aria-label="Filter by status"
            className="flex flex-wrap items-center overflow-hidden rounded-lg border border-grid-major bg-stock"
          >
            {STATUS_FILTERS.map((f) => {
              const active = (f.value || '') === (status || '')
              return (
                <button
                  key={f.value || 'all'}
                  role="tab"
                  aria-selected={active}
                  tabIndex={active ? 0 : -1}
                  onClick={() => setFilter({ status: f.value })}
                  className={`legend cursor-pointer px-3 py-2 transition-colors ${
                    active
                      ? 'bg-ink text-stock'
                      : 'text-ink-2 hover:bg-stock-2 hover:text-ink'
                  }`}
                >
                  {f.label}
                </button>
              )
            })}
          </div>

          <label className="flex items-center gap-2">
            <span className="legend text-ink-3">Service</span>
            <select
              value={service}
              onChange={(e) => setFilter({ service: e.target.value })}
              className="data-tight cursor-pointer rounded-lg border border-grid-major bg-stock px-2 py-2 text-ink"
            >
              <option value="">All</option>
              {services.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.id}
                </option>
              ))}
            </select>
          </label>

          <div className="ml-auto flex items-center gap-5">
            <span className="data-tight text-ink-3">
              {state === 'snapshot' ? `${rows.length} shown · ${activeCount} active` : '—'}
            </span>
            <div className="flex items-center gap-3">
              <button
                onClick={previous}
                disabled={cursorStack.current.length === 0}
                className="legend cursor-pointer rounded-lg border border-grid-major px-3 py-2 text-ink-2 transition-colors hover:border-ink hover:text-ink disabled:cursor-default disabled:opacity-40"
              >
                Prev
              </button>
              <button
                onClick={next}
                disabled={!hasMore}
                className="legend cursor-pointer rounded-lg border border-grid-major px-3 py-2 text-ink transition-colors hover:border-ink disabled:cursor-default disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        </div>

        <section aria-label="Incident register" className="overflow-hidden rounded-lg border border-grid-major bg-stock">
          <div className="hidden grid-cols-[auto_repeat(3,minmax(0,1fr))] items-center gap-x-6 border-b border-grid-major px-4 py-2.5 sm:grid sm:rounded-lg sm:rounded-b-none">
            <span className="w-2 shrink-0" aria-hidden="true" />
            <span className="legend text-ink-3">Service</span>
            <span className="legend text-ink-3">First alert</span>
            <span className="legend text-ink-3">Status</span>
          </div>

          {error && state === 'offline' ? (
            <div className="flex min-h-[16rem] flex-col items-center justify-center px-6 text-center">
              <h3 className="section-type text-ink">Register interrupted</h3>
              <p className="prose-measure mt-2 text-[0.9375rem] leading-relaxed text-ink-2">
                {error} The instrument retries; new readings will settle here
                when the connection returns.
              </p>
              <button
                onClick={() => load(null)}
                className="legend mt-5 cursor-pointer rounded-lg border border-grid-major px-3 py-2 text-ink transition-colors hover:border-ink"
              >
                Retry now
              </button>
            </div>
          ) : state === 'loading' ? (
            <LoadingRows />
          ) : rows.length === 0 ? (
            <div className="flex min-h-[16rem] flex-col items-center justify-center px-6 text-center">
              <h3 className="section-type text-ink">No incidents on record</h3>
              <p className="prose-measure mt-2 text-[0.9375rem] leading-relaxed text-ink-2">
                {status || service
                  ? 'Nothing matches the current filter. Widen the status or service to read more of the register.'
                  : 'Every signal is within threshold. New alerts will be logged here the moment an investigation starts.'}
              </p>
            </div>
          ) : (
            <ol className="divide-y divide-grid-minor">
              {rows.map((r) => (
                <RegisterRow key={r.id} incident={r} />
              ))}
            </ol>
          )}
        </section>
      </main>
    </div>
  )
}

function LoadingRows() {
  return (
    <div className="divide-y divide-grid-minor" aria-busy="true" aria-label="Loading register">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 px-4 py-4">
          <span className="h-2 w-2 animate-pulse bg-grid-major" />
          <span className="h-3 w-28 animate-pulse bg-stock-3" />
          <span className="h-3 flex-1 animate-pulse bg-stock-3" />
          <span className="h-3 w-24 animate-pulse bg-stock-3" />
        </div>
      ))}
    </div>
  )
}
