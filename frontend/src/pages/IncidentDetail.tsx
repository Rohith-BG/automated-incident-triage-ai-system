import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import BoardMasthead from '../components/BoardMasthead'
import RootCauseReport from '../components/RootCauseReport'
import {
  fetchIncident,
  STATUS_COLOR,
  STATUS_LABEL,
  isActiveStatus,
  type IncidentDetail,
  type IncidentStatus,
} from '../data/dashboard'
import { withAuthRetry } from '../lib/auth'
import { ApiError } from '../lib/api'
import { GateMark, StruckMark } from '../components/Icons'

type LoadState = 'loading' | 'ready' | 'not_found' | 'offline'

function StatusBadge({ status }: { status: string }) {
  const color = STATUS_COLOR[status as IncidentStatus] ?? 'var(--color-ink-3)'
  const pulse = isActiveStatus(status)
  return (
    <span
      className="data-tight inline-flex items-center gap-2 rounded-md border px-2.5 py-1"
      style={{ borderColor: color, color }}
    >
      <span
        className={`inline-block h-1.5 w-1.5 ${pulse ? 'animate-pulse' : ''}`}
        style={{ backgroundColor: color, borderRadius: 0 }}
        aria-hidden="true"
      />
      {STATUS_LABEL[status as IncidentStatus] ?? status}
    </span>
  )
}

function MetaItem({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-baseline gap-x-1.5">
      <span className="legend text-ink-3">{label}</span>
      <span className="data-tight text-ink-2">{value}</span>
    </span>
  )
}

function clockTime(iso: string): string {
  return new Date(iso).toLocaleString([], {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function IncidentDetail() {
  const { id = '' } = useParams()
  const [state, setState] = useState<LoadState>('loading')
  const [incident, setIncident] = useState<IncidentDetail | null>(null)

  useEffect(() => {
    let cancelled = false
    setState('loading')
    withAuthRetry(() => fetchIncident(id))
      .then((d) => {
        if (cancelled) return
        setIncident(d)
        setState('ready')
      })
      .catch((err: unknown) => {
        if (cancelled) return
        if (err instanceof ApiError && err.status === 404) {
          setState('not_found')
        } else {
          setState('offline')
        }
      })
    return () => {
      cancelled = true
    }
  }, [id])

  const report = incident?.report ?? null

  return (
    <div className="min-h-dvh">
      <BoardMasthead />

      <main className="mx-auto w-full max-w-[1400px] px-5 py-10 sm:px-8 lg:px-12">
        <Link
          to="/incidents"
          className="legend inline-flex items-center gap-2 text-ink-2 no-underline transition-colors hover:text-ink"
        >
          <span aria-hidden="true">←</span> Register
        </Link>

        {state === 'loading' ? (
          <LoadingState />
        ) : state === 'not_found' ? (
          <div className="mt-10 flex min-h-[18rem] flex-col items-center justify-center overflow-hidden rounded-lg border border-grid-major bg-stock px-6 text-center">
            <StruckMark className="text-tentative" />
            <h1 className="section-type mt-4 text-ink">No such investigation</h1>
            <p className="prose-measure mt-2 text-[0.9375rem] leading-relaxed text-ink-2">
              The register has no record for <span className="data-tight text-ink">{id}</span>.
              Return to the register to read what is on file.
            </p>
          </div>
        ) : state === 'offline' ? (
          <div className="mt-10 flex min-h-[18rem] flex-col items-center justify-center overflow-hidden rounded-lg border border-grid-major bg-stock px-6 text-center">
            <h1 className="section-type text-ink">Record unreachable</h1>
            <p className="prose-measure mt-2 text-[0.9375rem] leading-relaxed text-ink-2">
              The connection to the service dropped. Reload to read this record again.
            </p>
          </div>
        ) : incident ? (
          <>
            <header className="mb-8 mt-4">
              <div className="flex flex-wrap items-baseline gap-x-5 gap-y-2">
                <StatusBadge status={incident.status} />
                <MetaItem label="id" value={incident.id} />
                <MetaItem label="opened" value={clockTime(incident.created_at)} />
                <MetaItem label="updated" value={clockTime(incident.updated_at)} />
              </div>
              <h1 className="verdict-type mt-5 text-[clamp(1.9rem,4vw,3rem)]" style={{ maxWidth: '24ch' }}>
                {incident.service_id}
              </h1>
            </header>

            {report ? (
              <RootCauseReport report={report} />
            ) : (
              <WithheldState />
            )}

            <AlertsBlock alerts={incident.alerts} />
          </>
        ) : null}
      </main>
    </div>
  )
}

function WithheldState() {
  return (
    <div className="overflow-hidden rounded-lg border border-grid-major bg-stock">
      <div className="flex items-center gap-3 border-b border-grid-major px-5 py-4">
        <GateMark className="text-tentative" />
        <h2 className="legend text-tentative">No verdict</h2>
      </div>
      <div className="px-5 py-6">
        <p className="prose-measure text-[1rem] leading-relaxed text-ink-2">
          The investigation produced no root-cause report, so no cause is named.
          Confidence did not clear the detection limit, or the report has not
          been written yet. The raw alerts are below; the instrument reports
          what it could not establish rather than guessing.
        </p>
      </div>
    </div>
  )
}

function AlertsBlock({ alerts }: { alerts: IncidentDetail['alerts'] }) {
  return (
    <section aria-label="Raw alerts" className="mt-8">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="legend text-ink">Raw alerts</h2>
        <span className="data-tight text-ink-3">{alerts.length} on file</span>
      </div>
      {alerts.length === 0 ? (
        <p className="rounded-lg border border-grid-major bg-stock px-5 py-6 text-[0.9375rem] leading-relaxed text-ink-2">
          No alerts attached to this record.
        </p>
      ) : (
        <ol className="divide-y divide-grid-minor overflow-hidden rounded-lg border border-grid-major bg-stock">
          {alerts.map((a) => (
            <li key={a.id} className="px-5 py-4">
              <div className="mb-1.5 flex flex-wrap items-center gap-x-4 gap-y-1">
                <span className="provenance">alerts</span>
                <span className="data-tight text-ink-3">{clockTime(a.created_at)}</span>
              </div>
              <p className="text-[0.9375rem] leading-relaxed text-ink">{a.alert_message}</p>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

function LoadingState() {
  return (
    <div className="mt-4 space-y-6" aria-busy="true" aria-label="Loading incident">
      <div className="h-10 w-64 animate-pulse bg-stock-3" />
      <div className="border border-grid-major bg-stock p-8">
        <div className="space-y-3">
          <div className="h-3 w-40 animate-pulse bg-stock-3" />
          <div className="h-3 w-full animate-pulse bg-stock-3" />
          <div className="h-3 w-3/4 animate-pulse bg-stock-3" />
        </div>
      </div>
    </div>
  )
}
