/**
 * Agent-workflow console at `/workflow`.
 *
 * The public readout of Sift's autonomous investigation agent. Every running
 * investigation is one record sheet; when two or more run simultaneously they
 * are all listed, so the operator sees the parallel runs co-register rather
 * than one at a time. Each sheet names the step the agent is executing right
 * now and streams that step's progress over WebSocket — never polled.
 *
 * All figures come from the backend API: the summary strip, every incident,
 * and every live step.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import BoardMasthead from '../components/BoardMasthead'
import WorkflowPipeline, { type ConnectionState } from '../components/WorkflowPipeline'
import {
  blankRun,
  evolveRun,
  fetchActiveIncidents,
  fetchTraceSummary,
  type ActiveRun,
} from '../data/workflow'
import type { IncidentSummary } from '../data/dashboard'
import { withAuthRetry } from '../lib/auth'
import { useIncidentStream, type ProgressEvent } from '../lib/websocket'

type LoadState = 'loading' | 'ready' | 'offline'

/** A single investigation owns its own WebSocket subscription. */
function WorkflowItem({
  incident,
  terminal,
}: {
  incident: IncidentSummary
  terminal: boolean
}) {
  const [run, setRun] = useState<ActiveRun>(() => ({ ...blankRun(incident), terminal }))
  const [gateDone, setGateDone] = useState(false)
  const terminalRef = useRef(terminal)
  terminalRef.current = terminal

  const onProgress = useCallback((event: ProgressEvent) => {
    setRun((prev) => evolveRun(prev, event.event_type, event.message, event.details))
    if (event.event_type === 'gate_completed') setGateDone(true)
  }, [])

  // WS is held open while the run is active; a terminal incident freezes.
  const connection: ConnectionState = useIncidentStream(
    terminal ? null : incident.id,
    onProgress,
  )

  // Pull the aggregate tool-call summary once the detection rule has been met.
  useEffect(() => {
    if (!gateDone || run.traceSummary) return
    let cancelled = false
    withAuthRetry(() => fetchTraceSummary(incident.id))
      .then((s) => {
        if (!cancelled) setRun((prev) => (prev.traceSummary ? prev : { ...prev, traceSummary: s }))
      })
      .catch(() => {
        /* summary is best-effort; the panel degrades without it */
      })
    return () => {
      cancelled = true
    }
  }, [gateDone, incident.id, run.traceSummary])

  return <WorkflowPipeline run={run} connection={connection} />
}

/* ── Page ────────────────────────────────────────────────────────────── */

const POLL_MS = 5_000

export default function Workflow() {
  const [state, setState] = useState<LoadState>('loading')
  const [active, setActive] = useState<IncidentSummary[]>([])
  const [error, setError] = useState<string | null>(null)
  /** Runs that left the active set but are still shown so the finish is seen. */
  const [retired, setRetired] = useState<IncidentSummary[]>([])

  const timer = useRef<number | null>(null)
  const inFlight = useRef(false)

  const refresh = useCallback(async (isInitial = false) => {
    if (inFlight.current) return
    inFlight.current = true
    if (isInitial) setState('loading')
    try {
      const incidents = await withAuthRetry(() => fetchActiveIncidents())
      const ids = new Set(incidents.map((i) => i.id))
      setActive(incidents)
      setError(null)
      setRetired((prev) => {
        const stillActive = prev.filter((p) => ids.has(p.id))
        return stillActive
      })
      setState('ready')
    } catch {
      setError('Could not reach the investigation pipeline.')
      setState('offline')
    } finally {
      inFlight.current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    refresh(true)
    timer.current = window.setInterval(() => refresh(false), POLL_MS)
    return () => {
      if (timer.current) window.clearInterval(timer.current)
    }
  }, [refresh])

  const running = active.filter((i) => i.status === 'investigating').length
  const awaitingVerdict = active.filter((i) => i.status === 'root_cause_identified').length

  return (
    <div className="min-h-dvh bg-white">
      <BoardMasthead surface="white" />

      <main className="mx-auto w-full max-w-[1400px] px-5 py-10 sm:px-8 lg:px-12">
        <header className="mb-8">
          <h1 className="verdict-type text-[clamp(2rem,4.5vw,3.25rem)]">Agent workflow</h1>
          <p className="mt-4 w-full text-justify text-[1.0625rem] leading-[1.65] text-ink-2">
            Sift investigates production incidents autonomously, from the first
            alert to a confidence scored root cause report. The agent workflow
            console shows that investigation in motion, streaming the step the
            agent is executing right now. When several incidents run at once,
            their investigations appear side by side.
          </p>
        </header>

        {/* summary strip */}
        <div className="mb-8 flex flex-col gap-4 sm:flex-row">
          <SummaryCell
            label="Running now"
            value={state === 'ready' ? String(running) : '—'}
            accent={running > 0}
          />
          <SummaryCell
            label="Awaiting verdict"
            value={state === 'ready' ? String(awaitingVerdict) : '—'}
          />
        </div>

        {state === 'loading' ? (
          <LoadingState />
        ) : state === 'offline' ? (
          <OfflineState error={error} onRetry={() => refresh(true)} />
        ) : active.length + retired.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="space-y-6">
            {running > 1 ? (
              <div className="flex items-center gap-3 rounded-xl border border-grid-major bg-white px-4 py-3">
                <span className="h-2 w-2 animate-pulse bg-signal" aria-hidden="true" />
                <span className="legend text-ink">
                  {running} investigations are running in parallel
                </span>
                <span className="data-tight ml-auto text-ink-3">
                  each sheet reports on its own run
                </span>
              </div>
            ) : null}

            <div className="space-y-6">
              {active.map((incident) => (
                <WorkflowItem key={incident.id} incident={incident} terminal={false} />
              ))}
              {retired
                .filter((incident) => !active.some((a) => a.id === incident.id))
                .map((incident) => (
                  <div key={incident.id} className="opacity-60">
                    <WorkflowItem key={incident.id} incident={incident} terminal />
                  </div>
                ))}
            </div>
          </div>
        )}
      </main>
    </div>
  )
}

function SummaryCell({
  label,
  value,
  accent = false,
}: {
  label: string
  value: string
  accent?: boolean
}) {
  return (
    <div className="flex w-full flex-col gap-1.5 rounded-xl border border-grid-major bg-white p-5 sm:w-[15rem]">
      <span className="legend text-ink-3">{label}</span>
      <div
        className="verdict-type text-[clamp(2.5rem,4.5vw,3.5rem)] text-ink"
        style={{ fontWeight: 900, ...(accent ? { color: 'var(--color-signal)' } : {}) }}
      >
        {value}
      </div>
    </div>
  )
}

function LoadingState() {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Loading workflow">
      {Array.from({ length: 2 }).map((_, i) => (
        <div key={i} className="rounded-xl border border-grid-major bg-white">
          <div className="flex items-center gap-4 border-b border-grid-major px-5 py-4">
            <span className="h-2 w-2 animate-pulse bg-grid-major" />
            <span className="h-3 w-40 animate-pulse bg-stock-3" />
          </div>
          <div className="space-y-4 px-5 py-6">
            {Array.from({ length: 5 }).map((_, j) => (
              <div key={j} className="h-3 animate-pulse bg-stock-3" style={{ width: `${70 - j * 8}%` }} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function OfflineState({ error, onRetry }: { error: string | null; onRetry: () => void }) {
  return (
    <div className="flex min-h-[18rem] flex-col items-center justify-center rounded-xl border border-grid-major bg-white px-6 text-center">
      <h3 className="section-type text-ink">Pipeline unreachable</h3>
      <p className="prose-measure mt-2 text-[0.9375rem] leading-relaxed text-ink-2">
        {error ?? 'The agent can not be reached from here.'} It retries on its
        own; new runs will appear when the connection returns.
      </p>
      <button
        onClick={onRetry}
        className="legend mt-5 cursor-pointer border border-grid-major px-3 py-2 text-ink transition-colors hover:border-ink"
      >
        Retry now
      </button>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="flex min-h-[18rem] flex-col items-center justify-center rounded-xl border border-grid-major bg-white px-6 text-center">
      <h3 className="section-type text-ink">No investigations running</h3>
      <p className="prose-measure mt-2 text-[0.9375rem] leading-relaxed text-ink-2">
        Every service is within threshold. When an alert fires, its investigation
        will land here and stream the agent’s steps as it works.
      </p>
    </div>
  )
}