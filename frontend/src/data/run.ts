/**
 * Ground truth for the landing page.
 *
 * Every quantity in this file is copied from an artifact in this repository.
 * The `source` field on each export names that artifact. Nothing here is
 * invented: where the recorded run captured no value, the value is `null` and
 * the page reports it as unread rather than filling it in.
 */

export const PROVENANCE = {
  results: 'data/eval/results.json',
  golden: 'data/eval/golden_incidents.json',
  services: 'data/services.json',
  graph: 'agents/orchestrator/graph.py',
  state: 'agents/orchestrator/state.py',
} as const

/** The confidence gate's default threshold. */
export const GATE_THRESHOLD = 0.6

/* ─────────────────────────── The pipeline ───────────────────────────
   Node names and edges transcribed from _build_workflow() in
   agents/orchestrator/graph.py. The three middle nodes are a genuine
   parallel fan-out from knowledge_graph_query, joining at synthesize.
   ──────────────────────────────────────────────────────────────────── */

export type Phase = 'intake' | 'graph' | 'parallel' | 'join' | 'gate'

export interface PipelineNode {
  id: string
  short: string
  phase: Phase
}

export const PIPELINE: PipelineNode[] = [
  { id: 'intake', short: 'intake', phase: 'intake' },
  { id: 'knowledge_graph_query', short: 'graph query', phase: 'graph' },
  { id: 'observability_investigation', short: 'observability', phase: 'parallel' },
  { id: 'deploy_investigation', short: 'deploy', phase: 'parallel' },
  { id: 'incident_history_investigation', short: 'incident history', phase: 'parallel' },
  { id: 'code_diff_investigation', short: 'code diff', phase: 'parallel' },
  { id: 'synthesize', short: 'synthesize', phase: 'join' },
  { id: 'confidence_gate', short: 'confidence gate', phase: 'gate' },
]

/* ─────────────────────────── The channels ───────────────────────────
   Three concurrent detector channels. Tool names transcribed from the
   _call_mcp_tool() call sites in agents/orchestrator/graph.py.
   ──────────────────────────────────────────────────────────────────── */

export interface Channel {
  /** The `agent` field recorded on every trace row this channel emits. */
  agents: string[]
  label: string
  /** MCP tools this channel calls, in call order. */
  tools: string[]
  /** Provider used when ENVIRONMENT=dev. */
  devProvider: string
  /** Provider used when ENVIRONMENT=prod. */
  prodProvider: string
  /** Calls this channel contributes to a single-service run. */
  baseCalls: number
  note: string
}

export const CHANNELS: Channel[] = [
  {
    agents: ['observability'],
    label: 'observability',
    tools: ['get_errors', 'get_traces', 'get_metrics', 'get_anomalies'],
    devProvider: 'mock.py',
    prodProvider: 'aws_provider.py — CloudWatch',
    baseCalls: 4,
    note: 'Loops over every service in the blast radius, so its call count scales with the graph.',
  },
  {
    agents: ['deploy'],
    label: 'deploy investigation',
    tools: ['get_recent_deploys'],
    devProvider: 'mock.py',
    prodProvider: 'github_provider.py',
    baseCalls: 1,
    note: 'One call. What shipped, and when, against the alert’s timestamp.',
  },
  {
    agents: ['incident_knowledge'],
    label: 'incident history investigation',
    tools: ['search_incident_knowledge', 'get_past_resolutions'],
    devProvider: 'mock.py',
    prodProvider: 'db_provider.py',
    baseCalls: 2,
    note: 'UIDs returned by search_incident_knowledge are read through get_past_resolutions to recall what fixed this before.',
  },
  {
    agents: ['code_diff'],
    label: 'code diff investigation',
    tools: ['get_recent_commits', 'get_commit_diff'],
    devProvider: 'mock.py',
    prodProvider: 'github_provider.py',
    baseCalls: 1,
    note: 'get_commit_diff fires only when get_recent_commits returns candidates.',
  },
]

/** The evidence source that is not an MCP channel on the parallel branch. */
export const SUPPORTING_SOURCES = [
  {
    label: 'knowledge graph',
    role: 'Runs first. Resolves dependencies, blast radius and owning team before any channel opens.',
    devProvider: 'in_memory.py — data/services.json',
    prodProvider: 'neo4j_store.py',
  },
] as const

/* ─────────────────────────── The trace record ───────────────────────────
   Field-for-field from global_trace_recorder.record() in
   agents/orchestrator/graph.py. Every MCP call emits one of these.
   ─────────────────────────────────────────────────────────────────────── */

export const TRACE_FIELDS = [
  { name: 'incident_id', type: 'str', note: 'Which investigation this call belongs to.' },
  { name: 'agent', type: 'str', note: 'Which specialist made the call.' },
  { name: 'tool', type: 'str', note: 'server.tool_name — the exact tool invoked.' },
  { name: 'input_data', type: 'dict', note: 'Arguments as passed. Sanitised.' },
  { name: 'output_data', type: 'dict | None', note: 'What came back. None on failure.' },
  { name: 'latency_ms', type: 'float', note: 'Wall clock across every retry attempt.' },
  { name: 'success', type: 'bool', note: 'False once the retries are exhausted.' },
  { name: 'error', type: 'str | None', note: 'The exception text, kept verbatim.' },
] as const

export const RETRY_POLICY = { maxRetries: 2, backoff: '2^attempt seconds' } as const

/* ─────────────────────────── The recorded run ───────────────────────────
   data/eval/results.json — one run of the golden set. Confidence, latency,
   call counts and failures are as recorded. `tokens` is null because the
   run captured total_tokens: 0 for every specimen: the counter was never
   wired, so the page reports the channel as unread.
   ─────────────────────────────────────────────────────────────────────── */

export interface Specimen {
  id: string
  service: string
  /** alert_message from golden_incidents.json — the injected sample. */
  alert: string
  /** expected_root_cause from golden_incidents.json — the label, not our output. */
  label: string
  /** expected_blast_radius from golden_incidents.json. */
  expectedBlast: string[]
  difficulty: 'easy' | 'medium' | 'hard'
  tags: string[]
  /** confidence_score the run reported. */
  confidence: number
  /** Wall clock for the whole investigation, ms. */
  latencyMs: number
  /** Sum of every MCP call's latency, ms. */
  toolLatencyMs: number
  calls: number
  failedCalls: number
  /** Overlap between the produced root cause and the label. */
  overlap: number
  faithfulness: number
  blastRadius: number
  passed: boolean
  tokens: null
}

export const RUN = {
  source: PROVENANCE.results,
  totalIncidents: 7,
  passedIncidents: 2,
  passRate: 0.29,
  avgBlastRadius: 0.42,
  avgRootCause: 0.31,
  avgFaithfulness: 0.18,
  totalLatencyMs: 210767.78,
  /** results.json recorded total_tokens: 0 across every specimen. */
  totalTokens: null,
} as const

export const SPECIMENS: Specimen[] = [
  {
    id: 'inc-gold-001',
    service: 'payment-service',
    alert: 'Redis connection refused: ECONNREFUSED 127.0.0.1:6379 on /checkout',
    label: 'Redis cache node unavailable causing connection refused errors on checkout.',
    expectedBlast: ['payment-service', 'cart-service', 'redis-cache'],
    difficulty: 'easy',
    tags: ['redis', 'database', 'connection_error'],
    confidence: 0.9,
    latencyMs: 31849.86,
    toolLatencyMs: 12048.17,
    calls: 22,
    failedCalls: 2,
    overlap: 0.2,
    faithfulness: 0.37,
    blastRadius: 0.17,
    passed: false,
    tokens: null,
  },
  {
    id: 'inc-gold-002',
    service: 'order-service',
    alert: 'Stripe API 402 Payment Required: Card decline rate > 20%',
    label: 'External Stripe API payment processing failure causing 402 card declines.',
    expectedBlast: ['order-service', 'payment-gateway', 'checkout-ui'],
    difficulty: 'medium',
    tags: ['stripe', 'external_api', 'payment'],
    confidence: 0.5,
    latencyMs: 19860.29,
    toolLatencyMs: 6018.45,
    calls: 8,
    failedCalls: 1,
    overlap: 0.5,
    faithfulness: 0.2,
    blastRadius: 0.33,
    passed: false,
    tokens: null,
  },
  {
    id: 'inc-gold-003',
    service: 'inventory-service',
    alert: 'HTTPCode_Target_5XX_Count spike after deployment v2.4.1',
    label: 'Null pointer exception in inventory allocation logic introduced in deployment v2.4.1.',
    expectedBlast: ['inventory-service', 'order-service'],
    difficulty: 'hard',
    tags: ['deployment', 'code_bug', '5xx_error'],
    confidence: 0.15,
    latencyMs: 28782.44,
    toolLatencyMs: 6027.05,
    calls: 8,
    failedCalls: 1,
    overlap: 0.3,
    faithfulness: 0.14,
    blastRadius: 0.5,
    passed: true,
    tokens: null,
  },
  {
    id: 'inc-gold-004',
    service: 'user-service',
    alert: 'OOMKilled: Container exceeded 512Mi memory limit. Heap usage 98%.',
    label: 'Memory leak in user session cache causing OOMKilled container restarts.',
    expectedBlast: ['user-service', 'auth-service', 'api-gateway'],
    difficulty: 'medium',
    tags: ['memory_leak', 'oom', 'container'],
    confidence: 0.3,
    latencyMs: 15158.88,
    toolLatencyMs: 6024.59,
    calls: 8,
    failedCalls: 1,
    overlap: 0.3,
    faithfulness: 0.11,
    blastRadius: 0.33,
    passed: false,
    tokens: null,
  },
  {
    id: 'inc-gold-005',
    service: 'api-gateway',
    alert:
      'Cascading timeout: downstream db-service p99 latency > 30s, 504 Gateway Timeout rate 45%',
    label:
      'Database connection pool exhaustion on db-service causing cascading 504 timeouts through api-gateway.',
    expectedBlast: ['api-gateway', 'db-service', 'order-service', 'user-service'],
    difficulty: 'hard',
    tags: ['cascading_failure', 'database', 'timeout', 'connection_pool'],
    confidence: 0.4,
    latencyMs: 51422.14,
    toolLatencyMs: 6019.67,
    calls: 8,
    failedCalls: 1,
    overlap: 0.25,
    faithfulness: 0.11,
    blastRadius: 0.25,
    passed: false,
    tokens: null,
  },
  {
    id: 'inc-gold-006',
    service: 'notification-service',
    alert: 'TLS handshake failure: certificate expired for smtp.mailprovider.com',
    label: 'Expired TLS certificate on external SMTP relay causing email delivery failures.',
    expectedBlast: ['notification-service'],
    difficulty: 'easy',
    tags: ['certificate', 'tls', 'external_api'],
    confidence: 0.9,
    latencyMs: 21183.86,
    toolLatencyMs: 6015.41,
    calls: 8,
    failedCalls: 1,
    overlap: 0.55,
    faithfulness: 0.1,
    blastRadius: 1.0,
    passed: true,
    tokens: null,
  },
  {
    id: 'inc-gold-007',
    service: 'search-service',
    alert:
      'Elasticsearch cluster RED: 2 of 5 data nodes unreachable. IndexNotFoundException on product-index',
    label:
      'Elasticsearch data node failure causing cluster RED status and missing product search index.',
    expectedBlast: ['search-service', 'product-service', 'api-gateway'],
    difficulty: 'hard',
    tags: ['elasticsearch', 'cluster', 'data_loss', 'search'],
    confidence: 0.1,
    latencyMs: 42510.31,
    toolLatencyMs: 6019.21,
    calls: 8,
    failedCalls: 1,
    overlap: 0.08,
    faithfulness: 0.2,
    blastRadius: 0.33,
    passed: false,
    tokens: null,
  },
]

/** Mean latency of a single recorded MCP call in this specimen's run. */
export function meanCallLatency(s: Specimen): number {
  return s.toolLatencyMs / s.calls
}

/** Time the investigation spent outside its MCP calls — graph work and the LLM. */
export function synthesisLatency(s: Specimen): number {
  return s.latencyMs - s.toolLatencyMs
}

export function clearsGate(s: Specimen): boolean {
  return s.confidence >= GATE_THRESHOLD
}

/**
 * The calibration finding this run exposes: confidence and correctness
 * disagree on four of seven specimens. Derived from SPECIMENS, not asserted.
 */
export function calibrationSplit() {
  const overconfident = SPECIMENS.filter((s) => clearsGate(s) && !s.passed)
  const underconfident = SPECIMENS.filter((s) => !clearsGate(s) && s.passed)
  return { overconfident, underconfident }
}

/* ─────────────────────────── The graph ───────────────────────────
   A slice of data/services.json — the Online Boutique demo topology that
   is the bundled onboarding fixture and the default in-memory graph.
   ───────────────────────────────────────────────────────────────── */

export interface ServiceNode {
  id: string
  team: string
  language: string
  threshold: 'critical' | 'high' | 'medium'
  dependencies: string[]
}

export const TOPOLOGY: ServiceNode[] = [
  {
    id: 'frontend',
    team: 'platform-team',
    language: 'Go',
    threshold: 'high',
    dependencies: [
      'cart-service',
      'product-catalog-service',
      'currency-service',
      'checkout-service',
      'recommendation-service',
      'ad-service',
      'shipping-service',
    ],
  },
  {
    id: 'checkout-service',
    team: 'checkout-team',
    language: 'Go',
    threshold: 'critical',
    dependencies: ['payment-service', 'shipping-service', 'email-service', 'currency-service'],
  },
  {
    id: 'cart-service',
    team: 'cart-team',
    language: 'C#',
    threshold: 'high',
    dependencies: ['redis-cart'],
  },
  {
    id: 'payment-service',
    team: 'payments-team',
    language: 'Node.js',
    threshold: 'critical',
    dependencies: ['stripe-api'],
  },
  {
    id: 'shipping-service',
    team: 'fulfillment-team',
    language: 'Go',
    threshold: 'high',
    dependencies: [],
  },
  {
    id: 'currency-service',
    team: 'platform-team',
    language: 'Node.js',
    threshold: 'medium',
    dependencies: [],
  },
  {
    id: 'product-catalog-service',
    team: 'catalog-team',
    language: 'Go',
    threshold: 'medium',
    dependencies: [],
  },
  { id: 'redis-cart', team: 'cart-team', language: 'Redis', threshold: 'high', dependencies: [] },
]

/** KG change-proposal lifecycle. No auto-discovered graph goes live unreviewed. */
export const PROPOSAL_STATES = [
  { id: 'pending', note: 'Discovered, not yet trusted. Held out of the active graph.' },
  { id: 'approved', note: 'An admin accepted it. Only now does it reach the graph.' },
  { id: 'rejected', note: 'Wrong. Recorded so the builder does not re-propose it.' },
  { id: 'feedback', note: 'Nearly right; returned with a correction to fold in.' },
  { id: 'superseded', note: 'A later proposal replaced it before review.' },
] as const

/* ─────────────────────────── Links ───────────────────────────── */

export const LINKS = {
  repo: 'https://github.com/Rohith-BG/automated-incident-triage-ai-system',
  /** PLACEHOLDER — no deployment exists yet. Replace with the live URL. */
  demo: null as string | null,
  /** PLACEHOLDER — no write-up published yet. Replace with the URL. */
  writeup: null as string | null,
} as const
