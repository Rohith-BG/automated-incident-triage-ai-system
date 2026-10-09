import { LINKS } from '../data/run'
import { Offsheet, Wordmark } from './Icons'

const STANDING = [
  {
    state: 'architecture',
    items: [
      'Five independent evidence channels — observability, deployments, incident knowledge, code diffs, and the service graph — investigated in parallel via in-process MCP servers.',
      'Confidence-gated verdicts: a cause is named only when the collected evidence supports it; the report states plainly when the evidence ran out rather than guessing.',
      'Dual architecture support: microservice and monolith investigations through one pipeline.',
    ],
  },
  {
    state: 'delivery',
    items: [
      'FastAPI backend with async workers and WebSocket live progress — alert ingestion to verdict in a single pipeline.',
      'SQS-backed workers with idempotent processing, exponential backoff, and a dead-letter queue for poison messages.',
      'JWT authentication with role-based access control and team-scoped incident visibility.',
    ],
  },
  {
    state: 'traceability',
    items: [
      'Every MCP tool call is recorded: arguments in, result out, latency, success state, and exception text on failure.',
      'Agent reasoning is inspectable end to end — from alert ingestion to the final causal verdict, surfaced through REST and WebSocket.',
      'Token usage is captured per call when the LLM provider supplies it.',
    ],
  },
]

export default function Close() {
  return (
    <footer className="bg-stock-2 text-ink">
      <div className="disclosure-bands mx-auto w-full max-w-[1400px] px-5 py-16 sm:px-8 lg:px-12 lg:py-20">
        <div className="grid gap-x-14 gap-y-10 lg:grid-cols-[minmax(0,30rem)_minmax(0,1fr)]">
          <div>
            <h2
              className="verdict-type text-[clamp(1.9rem,4vw,3.1rem)] text-ink"
              style={{ maxWidth: '20ch' }}
            >
              Production-grade incident triage.
            </h2>
            <p className="prose-measure mt-5 text-[1.0625rem] leading-[1.6] text-ink-2">
              Sift is built to deploy: a multi-agent investigation pipeline, service knowledge
              graph, confidence-gated verdicts with uncertainty reporting, and full traceability
              on every tool call. The backend, the agents, the evaluation harness, and this
              landing page ship in the same repository.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <a className="action-primary" href={LINKS.repo} target="_blank" rel="noreferrer">
                Read the source
                <Offsheet />
              </a>
            </div>
          </div>

          <div>
            <h3 className="legend text-ink">Under the hood</h3>
            <dl className="mt-4">
              {STANDING.map((group) => (
                <div
                  key={group.state}
                  className="band grid grid-cols-1 gap-x-6 gap-y-2 py-5 sm:grid-cols-[minmax(0,6rem)_minmax(0,1fr)]"
                >
                  <dt className="band-label text-ink-2">{group.state}</dt>
                  <dd className="m-0">
                    <ul className="m-0 list-none space-y-1.5 p-0">
                      {group.items.map((it) => (
                        <li key={it} className="text-[0.875rem] leading-relaxed text-ink-2">
                          {it}
                        </li>
                      ))}
                    </ul>
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        </div>

        <div
          id="source"
          className="mt-14 flex flex-wrap items-center justify-between gap-5 border-t border-ink pt-6 scroll-mt-16"
        >
          <span className="text-ink">
            <Wordmark />
          </span>
          <p className="data-tight max-w-[46ch] text-ink-2">
            Automated incident triage and root-cause investigation. Evidence-grounded, confidence
            scored, and inspectable end to end.
          </p>
          <a
            href={LINKS.repo}
            target="_blank"
            rel="noreferrer"
            className="legend inline-flex items-center gap-2 text-ink no-underline transition-colors hover:text-signal"
          >
            github
            <Offsheet className="opacity-70" />
          </a>
        </div>
      </div>
    </footer>
  )
}