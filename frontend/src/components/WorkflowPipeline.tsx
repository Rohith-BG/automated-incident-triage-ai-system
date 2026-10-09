/**
 * A single live investigation rendered as a current-activity readout.
 *
 * One incident's agent run, drawn as a record sheet rather than a pipe: a
 * "now" band that names the exact step the agent is executing this moment,
 * followed by the full agent lifecycle as a ledger — queue hand-over, intake,
 * knowledge graph, the three parallel evidence channels, synthesis, and the
 * confidence gate. Each step carries a done / in-flight / queued marker; the
 * live step alone takes the signal red.
 *
 * The panel is honest about how much the stream has actually reported: a run
 * whose link is open but that has delivered no events reads as the queue
 * hand-over still in flight, a run with events flowing reads as live, and a
 * run that left the active set reads as frozen in the record.
 */

import { Link } from 'react-router-dom'
import {
  agentStepStates,
  type ActiveRun,
  type AgentStepState,
  type AgentStepRun,
} from '../data/workflow'
import { isActiveStatus, STATUS_COLOR, STATUS_LABEL, type IncidentStatus } from '../data/dashboard'
import { ms } from '../lib/format'
import { PeakMark, StruckMark } from './Icons'

function clockTime(iso: string): string {
  return new Date(iso).toLocaleString([], {
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/* The plotted marker for one ledger step: hollow queued, lit in-flight, ticked. */
function StepMarker({ run }: { run: AgentStepRun }) {
  if (run === 'done') {
    return (
      <span
        className="inline-flex h-4 w-4 items-center justify-center bg-ink"
        aria-hidden="true"
      >
        <PeakMark className="h-3 w-3 text-white" />
      </span>
    )
  }
  if (run === 'doing') {
    return (
      <span
        className="inline-flex h-4 w-4 items-center justify-center border border-current"
        style={{ color: 'var(--color-signal)' }}
        aria-hidden="true"
      >
        <span className="h-2 w-2 animate-pulse bg-current" />
      </span>
    )
  }
  return (
    <span
      className="inline-flex h-4 w-4 items-center justify-center border border-current"
      style={{ color: 'var(--color-ink-3)' }}
      aria-hidden="true"
    />
  )
}

function GateVerdict({ state }: { state: AgentStepState }) {
  if (state.run !== 'done') return null
  const details = state.details as Record<string, unknown> | undefined
  const passed = details?.passed as boolean | undefined
  const score = details?.confidence_score as number | undefined
  if (typeof passed === 'boolean' && typeof score === 'number') {
    return passed ? (
      <span className="data-tight flex items-center gap-2 text-signal">
        <PeakMark className="h-3 w-3" />
        PASSED · {score.toFixed(2)}
      </span>
    ) : (
      <span className="data-tight flex items-center gap-2 text-tentative">
        <StruckMark className="h-3 w-3" />
        BELOW DETECTION · {score.toFixed(2)}
      </span>
    )
  }
  return null
}

/* One ledger row: marker, step name and description, live message, verdict. */
function StepRow({ state, live }: { state: AgentStepState; live: boolean }) {
  const { def, run } = state
  const active = run === 'doing' && live
  const faint = run === 'queued'
  return (
    <li className="grid grid-cols-[1.5rem,minmax(0,1fr),auto] items-start gap-x-4 border-b border-grid-minor py-3.5 last:border-0">
      <div className="mt-[0.15rem]">
        <StepMarker run={run} />
      </div>
      <div className="min-w-0">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
          <span
            className={`text-[0.9375rem] font-semibold tracking-[-0.01em] ${
              active ? 'text-signal' : faint ? 'text-ink-3' : 'text-ink'
            }`}
          >
            {def.label}
          </span>
          {active ? <span className="legend text-signal">in progress</span> : null}
        </div>
        <p className={`mt-1 text-[0.8125rem] leading-snug ${faint ? 'text-ink-3' : 'text-ink-2'}`}>
          {def.does}
        </p>
        {state.message ? (
          <p className="data-tight mt-1.5 leading-relaxed text-ink-2">{state.message}</p>
        ) : null}
      </div>
      {def.id === 'gate' ? <GateVerdict state={state} /> : null}
    </li>
  )
}

/* The parallel evidence channels share one grouped ledger entry. */
function ParallelSteps({ states, live }: { states: AgentStepState[]; live: boolean }) {
  return (
    <li className="border-b border-grid-minor py-4">
      <span className="legend text-ink-3">Evidence — runs in parallel</span>
      <ul className="mt-3 grid gap-3 sm:grid-cols-3">
        {states.map((state) => (
          <li key={state.def.id} className="rounded-xl border border-grid-minor px-4 py-3">
            <div className="flex items-center gap-2.5">
              <StepMarker run={state.run} />
              <span
                className={`truncate text-[0.875rem] font-semibold tracking-[-0.01em] ${
                  state.run === 'doing' && live ? 'text-signal' : 'text-ink'
                }`}
              >
                {state.def.label}
              </span>
            </div>
            <p className="mt-2 text-[0.7813rem] leading-snug text-ink-3">{state.def.does}</p>
            {state.message ? (
              <p className="data-tight mt-2 leading-relaxed text-ink-2">{state.message}</p>
            ) : null}
          </li>
        ))}
      </ul>
    </li>
  )
}

export type ConnectionState = 'connecting' | 'open' | 'closed'

export default function WorkflowPipeline({
  run,
  connection = 'open',
}: {
  run: ActiveRun
  connection?: ConnectionState
}) {
  const { incident } = run
  const active = isActiveStatus(incident.status)
  const status = incident.status as IncidentStatus
  const statusColor = STATUS_COLOR[status] ?? 'var(--color-ink-3)'
  const link = connection === 'open'
  /** Open connection but the run has not reported a single event yet. */
  const silent = link && !run.spoken
  const frozen = run.terminal
  const awaiting = connection !== 'open' || silent || frozen
  const connectionLabel = frozen
    ? 'frozen · in record'
    : connection === 'connecting'
      ? 'link · establishing'
      : connection === 'closed'
        ? 'link · lost — retrying'
        : silent
          ? 'armed · awaiting run events'
          : 'live'

  const states = agentStepStates(run)
  const now = states.find((s) => s.run === 'doing') ?? null
  const gateState = states.find((s) => s.def.id === 'gate')
  const gateDone = gateState?.run === 'done'

  let bandTitle: string
  let bandBody: string | null = null
  if (gateDone) {
    bandTitle = 'Confidence gate — verdict issued'
    bandBody = gateState?.message ?? 'The report has been scored against the detection threshold.'
  } else if (frozen) {
    bandTitle = 'Frozen — in record'
    bandBody = run.lastMessage ?? 'The run left the active set; the readout is preserved as reported.'
  } else if (now) {
    bandTitle = `Now — ${now.def.performing}`
    bandBody = now.message ?? (silent ? 'Awaiting the first progress event…' : null)
  } else {
    bandTitle = 'Awaiting the agent’s next step'
    bandBody = null
  }

  const firstSteps = states.filter(
    (s) => !s.def.parallel && s.def.id !== 'synthesize' && s.def.id !== 'gate',
  )
  const parallelSteps = states.filter((s) => s.def.parallel)
  const finalSteps = states.filter((s) => s.def.id === 'synthesize' || s.def.id === 'gate')
  const live = !frozen && !silent

  return (
    <section
      aria-label={`Investigation ${incident.id}`}
      className="rounded-xl border border-grid-major bg-white"
    >
      {/* header: the alert this run is resolving */}
      <header className="border-b border-grid-major px-5 py-4">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <span
            className={`inline-block h-2 w-2 shrink-0 ${active ? 'animate-pulse' : ''}`}
            style={{ backgroundColor: statusColor, borderRadius: 0 }}
            aria-hidden="true"
          />
          <span className="legend text-ink">{STATUS_LABEL[status] ?? incident.status}</span>
          <span className="data-tight text-ink-3">incident · {incident.id}</span>
          <span className="data-tight text-ink-3">opened · {clockTime(incident.created_at)}</span>
          <span
            className={`legend ml-auto inline-flex items-center gap-2 ${
              awaiting ? 'text-tentative' : 'text-ink-2'
            }`}
          >
            <span
              className={`inline-block h-1.5 w-1.5 rounded-none ${
                connection === 'closed' || silent ? 'animate-pulse' : ''
              }`}
              style={{
                backgroundColor: awaiting ? 'var(--color-tentative)' : 'var(--color-ink-3)',
              }}
              aria-hidden="true"
            />
            {connectionLabel}
          </span>
          <Link
            to={`/incidents/${incident.id}`}
            className="legend inline-flex items-center gap-2 text-ink-2 no-underline transition-colors hover:text-ink"
          >
            Open in register <span aria-hidden="true">→</span>
          </Link>
        </div>
        <h3 className="section-type mt-3 text-[1.35rem] text-ink">{incident.service_id}</h3>
      </header>

      <div className="px-5 py-6">
        {/* the current-activity band */}
        <div className="flex items-start gap-4">
          <div className="mt-[0.15rem]">
            <StepMarker run="doing" />
          </div>
          <div className="min-w-0 flex-1">
            <h4 className="verdict-type text-[clamp(1.35rem,2.4vw,1.8rem)] text-ink">
              {bandTitle}
            </h4>
            {bandBody ? (
              <p
                className={`data-tight mt-2 max-w-[60ch] leading-relaxed ${
                  now?.run === 'doing' && !frozen ? 'text-ink-2' : 'text-ink-3'
                }`}
              >
                {bandBody}
              </p>
            ) : null}
          </div>
        </div>

        {/* the agent lifecycle ledger */}
        <ol className="mt-7">
          {firstSteps.map((state) => (
            <StepRow key={state.def.id} state={state} live={live} />
          ))}
          <ParallelSteps states={parallelSteps} live={live} />
          {finalSteps.map((state) => (
            <StepRow key={state.def.id} state={state} live={live} />
          ))}
        </ol>
      </div>

      {/* footer datum strip */}
      <footer className="flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-grid-minor px-5 py-3">
        <span className="data-tight text-ink-3">
          run id · <span className="text-ink">{incident.id}</span>
        </span>
        {run.traceSummary ? (
          <>
            <span className="data-tight text-ink-3">
              tool calls · <span className="text-ink">{run.traceSummary.total_calls}</span>
            </span>
            <span className="data-tight text-ink-3">
              latency · <span className="text-ink">{ms(run.traceSummary.total_latency_ms)}</span>
            </span>
            <span
              className={`data-tight ${
                run.traceSummary.failed_calls > 0 ? 'text-tentative' : 'text-ink-3'
              }`}
            >
              failed calls · {run.traceSummary.failed_calls}
            </span>
          </>
        ) : (
          <span className="data-tight text-ink-3">trace summary pending</span>
        )}
      </footer>
    </section>
  )
}