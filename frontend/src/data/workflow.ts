/**
 * Agent-workflow domain types and live-state reducer.
 *
 * A single investigation is an 8-step agent lifecycle, from the message-queue
 * hand-over through the 7-node LangGraph pipeline:
 *   queue → intake → knowledge_graph_query
 *   → (observability ‖ deploy ‖ knowledge_diff, parallel)
 *   → synthesize → confidence_gate
 *
 * Live progress arrives over one WebSocket per incident. Each `ProgressEvent`
 * (`{event_type, message, details}`) maps to a stage transition, and the reducer
 * here turns that stream into the per-step read state the readout card draws.
 *
 * Mirrors the orchestrator event names in agents/orchestrator/graph.py.
 */

import { api } from '../lib/api'
import type { IncidentSummary } from './dashboard'

/* ── Pipeline model ─────────────────────────────────────────────────── */

export type PipelineStageId =
  | 'intake'
  | 'knowledge_graph_query'
  | 'observability'
  | 'deploy'
  | 'knowledge_diff'
  | 'synthesize'
  | 'confidence_gate'

export type StageRunState = 'pending' | 'running' | 'complete'

export interface StageState {
  id: PipelineStageId
  /** Short instrument label rendered beside the marker. */
  label: string
  /** Human note reported by the orchestrator at this stage. */
  message?: string
  /** Typed detail payload from the most recent progress event. */
  details?: Record<string, unknown>
  run: StageRunState
}

/** The three stages that fan out and run in parallel after the KG query. */
export const PARALLEL_STAGE_IDS: readonly PipelineStageId[] = [
  'observability',
  'deploy',
  'knowledge_diff',
] as const

export type PipelinePhase = 'intake' | 'graph' | 'parallel' | 'synthesize' | 'gate'

export interface ActiveRun {
  incident: IncidentSummary
  /** Per-stage live state, keyed by stage id. */
  stages: Record<PipelineStageId, StageState>
  /** Most recent raw progress message (used for the arming/status line). */
  lastMessage?: string
  /** True once the WS has delivered at least one event for this incident. */
  spoken: boolean
  /** Aggregate tool-call summary, populated once the run finishes. */
  traceSummary?: TraceSummary
  /** True once the incident left the active set (so we freeze the panel). */
  terminal: boolean
}

export interface TraceSummary {
  total_calls: number
  total_latency_ms: number
  total_tokens: number
  failed_calls: number
}

/* ── Stage registry ─────────────────────────────────────────────────── */

/**
 * Ordered, labelled stage definitions. `parallel` stages share the same rail
 * position and are grouped in the panel; everything else is a single rail row.
 */
export const STAGE_DEFS: ReadonlyArray<{
  id: PipelineStageId
  label: string
  phase: PipelinePhase
}> = [
  { id: 'intake', label: 'Intake', phase: 'intake' },
  { id: 'knowledge_graph_query', label: 'Knowledge graph', phase: 'graph' },
  { id: 'observability', label: 'Observability', phase: 'parallel' },
  { id: 'deploy', label: 'Deploy', phase: 'parallel' },
  { id: 'knowledge_diff', label: 'Knowledge + diff', phase: 'parallel' },
  { id: 'synthesize', label: 'Synthesize', phase: 'synthesize' },
  { id: 'confidence_gate', label: 'Confidence gate', phase: 'gate' },
]

/** The confidence detection limit, transcribed from AgentSettings default. */
export const CONFIDENCE_THRESHOLD = 0.6

/* ── Agent-step ledger ─────────────────────────────────────────────── */

export type AgentStepId =
  | 'queue'
  | 'intake'
  | 'kg'
  | 'observability'
  | 'deploy'
  | 'knowledge_diff'
  | 'synthesize'
  | 'gate'

export type AgentStepRun = 'done' | 'doing' | 'queued'

export interface AgentStepDef {
  id: AgentStepId
  /** Orchestrator stage this step tracks; absent only for the queue hand-over. */
  stageId?: PipelineStageId
  /** Short ledger name for the step. */
  label: string
  /** One line on what the step does, shown in the ledger. */
  does: string
  /** The "now" line: what the agent is doing while the step is live. */
  performing: string
  /** True when the step runs concurrently with its siblings (post-KG fan-out). */
  parallel?: boolean
}

/**
 * The agent lifecycle in presentation order, beginning with the queue-consumer
 * hand-over and ending at the confidence gate. Mirrors the orchestrator nodes
 * in agents/orchestrator/graph.py.
 */
export const AGENT_STEPS: readonly AgentStepDef[] = [
  {
    id: 'queue',
    label: 'Consume from message queue',
    does: 'Hands the alert from the message queue to the investigation orchestrator.',
    performing: 'reading the alert off the message queue',
  },
  {
    id: 'intake',
    stageId: 'intake',
    label: 'Intake',
    does: 'Resolves the service, its architecture type, and the graph entry point.',
    performing: 'resolving the service, its architecture, and the entry point',
  },
  {
    id: 'kg',
    stageId: 'knowledge_graph_query',
    label: 'Knowledge graph',
    does: 'Queries the graph for blast radius, dependencies, owner, and history.',
    performing: 'querying the knowledge graph for blast radius and dependencies',
  },
  {
    id: 'observability',
    stageId: 'observability',
    label: 'Observability',
    parallel: true,
    does: 'Collects logs, errors, traces, metrics, and anomalies across the blast radius.',
    performing: 'collecting logs, errors, traces, metrics, and anomalies',
  },
  {
    id: 'deploy',
    stageId: 'deploy',
    label: 'Deploys',
    parallel: true,
    does: 'Checks recent deployments of the service and its dependencies.',
    performing: 'checking the recent deployment history',
  },
  {
    id: 'knowledge_diff',
    stageId: 'knowledge_diff',
    label: 'Knowledge + code diff',
    parallel: true,
    does: 'Searches runbooks, past resolutions, and recent code commits.',
    performing: 'searching runbooks and recent code commit diffs',
  },
  {
    id: 'synthesize',
    stageId: 'synthesize',
    label: 'Synthesize',
    does: 'Drafts the evidence-grounded root-cause report.',
    performing: 'synthesizing the evidence-grounded root-cause report',
  },
  {
    id: 'gate',
    stageId: 'confidence_gate',
    label: 'Confidence gate',
    does: 'Scores the report against the confidence threshold for a verdict.',
    performing: 'checking the report against the confidence threshold',
  },
]

export interface AgentStepState {
  def: AgentStepDef
  run: AgentStepRun
  message?: string
  details?: Record<string, unknown>
}

/** Resolve every ledger step's live state from the run's stage states. */
export function agentStepStates(run: ActiveRun): AgentStepState[] {
  return AGENT_STEPS.map((def): AgentStepState => {
    if (!def.stageId) {
      // The queue hand-over happens once. Until the run reports its first
      // event it is the step in flight; after that it is in the record.
      return { def, run: run.spoken ? 'done' : 'doing' }
    }
    const stage = run.stages[def.stageId]
    const runState: AgentStepRun =
      stage.run === 'complete' ? 'done' : stage.run === 'running' ? 'doing' : 'queued'
    return { def, run: runState, message: stage.message, details: stage.details }
  })
}

/** The single step the agent is executing right now, or null when none is live. */
export function currentStep(run: ActiveRun): AgentStepState | null {
  return agentStepStates(run).find((s) => s.run === 'doing') ?? null
}

/* ── State construction ─────────────────────────────────────────────── */

function pendingStages(): Record<PipelineStageId, StageState> {
  const map = {} as Record<PipelineStageId, StageState>
  for (const def of STAGE_DEFS) {
    map[def.id] = { id: def.id, label: def.label, run: 'pending' }
  }
  return map
}

export function blankRun(incident: IncidentSummary): ActiveRun {
  // No stage has reported yet: the queue hand-over is the step in flight and
  // every orchestrator stage is still queued behind it.
  return { incident, stages: pendingStages(), spoken: false, terminal: false }
}

/**
 * Map an orchestrator `event_type` to the stage it belongs to, or null when
 * the event is not a node transition (e.g. a stray keep-alive frame).
 */
function stageForEventType(eventType: string): PipelineStageId | null {
  switch (eventType.replace(/_(started|completed)$/, '')) {
    case 'intake':
      return 'intake'
    case 'kg':
      return 'knowledge_graph_query'
    case 'observability':
      return 'observability'
    case 'deploy':
      return 'deploy'
    case 'knowledge_diff':
      return 'knowledge_diff'
    case 'synthesis':
      return 'synthesize'
    case 'gate':
      return 'confidence_gate'
    default:
      return null
  }
}

/**
 * Fold one WebSocket progress event into a live run. Returns a new `ActiveRun`
 * when the event produced a visible change, or the same reference otherwise.
 */
export function evolveRun(
  run: ActiveRun,
  eventType: string,
  message: string | undefined,
  details: Record<string, unknown> | undefined,
): ActiveRun {
  const stageId = stageForEventType(eventType)
  if (!stageId) return run

  const completing = eventType.endsWith('_completed')
  const nextRunState: StageRunState = completing ? 'complete' : 'running'

  const current = run.stages[stageId]
  const next: StageState = {
    ...current,
    run: nextRunState,
    message: message ?? current.message,
    // Completion payloads carry the useful evidence; started payloads mostly
    // repeat context. Keep the richer of the two.
    details: details && Object.keys(details).length > 0 ? details : current.details,
  }

  const stages = { ...run.stages, [stageId]: next }
  return {
    ...run,
    stages,
    lastMessage: message ?? run.lastMessage,
    spoken: true,
  }
}

/* ── API calls ─────────────────────────────────────────────────────── */

export async function fetchActiveIncidents(): Promise<IncidentSummary[]> {
  const page = await api.get<{
    items: IncidentSummary[]
    next_cursor: string | null
    has_more: boolean
    limit: number
  }>('/incidents?limit=100')
  return page.items.filter(
    (i) => i.status === 'investigating' || i.status === 'root_cause_identified',
  )
}

export async function fetchTraceSummary(id: string): Promise<TraceSummary> {
  const res = await api.get<{ summary: TraceSummary }>(`/incidents/${id}/traces`)
  return res.summary
}
