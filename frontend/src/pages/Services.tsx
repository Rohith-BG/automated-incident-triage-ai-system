import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import BoardMasthead from '../components/BoardMasthead'
import { LeaderArrow } from '../components/Icons'
import { withAuthRetry } from '../lib/auth'
import { fetchServiceRegistry, type RegistryService } from '../data/service_registry'
import { fetchActiveGraph, type KgSnapshot } from '../data/kg'

type LoadState = 'loading' | 'ready'

interface CatalogData {
  registry: RegistryService[] | null
  graph: KgSnapshot | null
  registryNote: string | null
  graphNote: string | null
}

interface BlastInfo {
  /** Services that directly depend on this one (in-edges). */
  dependents: string[]
  /** Full blast radius: the service itself plus every transitive dependent. */
  blast: string[]
}

function computeBlast(graph: KgSnapshot): Map<string, BlastInfo> {
  const edges = graph.edges.filter((e) => e.type === 'DEPENDS_ON')
  const dependents = new Map<string, string[]>()
  for (const e of edges) {
    const list = dependents.get(e.to) ?? []
    list.push(e.from)
    dependents.set(e.to, list)
  }

  const result = new Map<string, BlastInfo>()
  const all = new Set(edges.flatMap((e) => [e.from, e.to]))
  for (const id of all) {
    const visited = new Set<string>()
    const queue: string[] = [id]
    let blast: string[] = []
    while (queue.length > 0) {
      const current = queue.shift() as string
      if (visited.has(current)) continue
      visited.add(current)
      if (current !== id) blast.push(current)
      for (const up of dependents.get(current) ?? []) {
        if (!visited.has(up)) queue.push(up)
      }
    }
    blast = blast.filter((b) => all.has(b))
    result.set(id, { dependents: dependents.get(id) ?? [], blast })
  }
  return result
}

const THRESHOLD_COLOR: Record<string, string> = {
  critical: 'var(--color-signal)',
  high: 'var(--color-phosphor)',
  medium: 'var(--color-ink)',
  low: 'var(--color-ink-3)',
}

export default function Services() {
  const [state, setState] = useState<LoadState>('loading')
  const [data, setData] = useState<CatalogData>({
    registry: null,
    graph: null,
    registryNote: null,
    graphNote: null,
  })

  const load = useCallback(async (): Promise<void> => {
    setState('loading')
    try {
      const [registryResult, graphResult] = await Promise.allSettled([
        withAuthRetry(() => fetchServiceRegistry()),
        withAuthRetry(() => fetchActiveGraph()),
      ])

      setData({
        registry:
          registryResult.status === 'fulfilled' ? registryResult.value : null,
        graph: graphResult.status === 'fulfilled' ? graphResult.value : null,
        registryNote:
          registryResult.status === 'rejected'
            ? 'The service registry could not be read from the database.'
            : null,
        graphNote:
          graphResult.status === 'rejected'
            ? 'The knowledge graph could not be read — dependencies and blast radius are reported unread.'
            : null,
      })
    } catch {
      /* both settled individually; nothing to add */
    }
    setState('ready')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const { registry, graph, registryNote, graphNote } = data
  const services = registry ?? []
  const nodes = graph?.nodes.length ?? null
  const edges = graph?.edges.length ?? null
  const blast = graph != null ? computeBlast(graph) : null

  const graphKnown = graph != null
  const registryKnown = registry != null
  const registryEmpty = registryKnown && services.length === 0
  const graphEmpty = graphKnown && nodes === 0

  const criticalCount = registry
    ? registry.filter((s) => s.alert_threshold === 'critical').length
    : null

  return (
    <div className="min-h-dvh bg-stock">
      <BoardMasthead />

      <main className="mx-auto w-full max-w-[1400px] px-5 py-10 sm:px-8 lg:px-12">
        <header className="mb-8">
          <h1 className="verdict-type text-[clamp(2rem,4.5vw,3.25rem)]">Services</h1>
          <p className="mt-3 max-w-full text-[1.0625rem] leading-[1.6] text-ink-2">
            Browse every service under triage: ownership, runtime stack, alert
            threshold, and dependency blast radius at a glance. Select a service
            to open its full catalog details.
          </p>
        </header>

        {/* ── Status readout ── */}
        <section aria-label="Service catalog status" className="mt-2">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Readout
              label="Registered"
              value={
                state === 'ready'
                  ? registry != null
                    ? `${services.length} services`
                    : 'unread'
                  : 'reading…'
              }
            />
            <Readout
              label="Graph topology"
              value={
                state === 'ready'
                  ? nodes != null && edges != null
                    ? `${nodes} nodes · ${edges} edges`
                    : 'unread'
                  : 'reading…'
              }
            />
            <Readout
              label="Critical threshold"
              value={
                criticalCount != null
                  ? `${criticalCount} service${criticalCount === 1 ? '' : 's'}`
                  : 'unread'
              }
            />
            <Readout
              label="Dependencies"
              value={
                edges != null ? `${edges} recorded edge${edges === 1 ? '' : 's'}` : 'unread'
              }
            />
          </div>
          {(registryNote || graphNote) && state === 'ready' ? (
            <p className="mt-2 text-[0.8125rem] leading-snug text-ink-3">
              {registryNote}
              {registryNote && graphNote ? ' ' : ''}
              {graphNote}
            </p>
          ) : null}
        </section>

        {state === 'loading' ? (
          <LoadingRows />
        ) : registryEmpty ? (
          <div className="mt-8 flex min-h-[18rem] flex-col items-center justify-center rounded-2xl border border-grid-major bg-stock px-6 py-12 text-center">
            <p className="section-type text-ink">No services registered</p>
            <p className="prose-measure mx-auto mt-2 text-[0.9375rem] leading-relaxed text-ink-2">
              The registry has no rows yet. Register a service to see its
              catalog entry here.
            </p>
            {graphEmpty ? (
              <p className="prose-measure mx-auto mt-2 text-[0.9375rem] leading-relaxed text-ink-2">
                The active graph also has no nodes. Run a build and approve a
                proposal to grow it.
              </p>
            ) : null}
            <Link
              to="/graph/build"
              className="legend mt-5 inline-flex rounded-md border border-grid-major px-3 py-2 text-ink no-underline transition-colors hover:border-ink"
            >
              Build KG →
            </Link>
          </div>
        ) : (
          <section
            aria-label="Service register"
            className="mt-6 overflow-hidden rounded-xl border border-grid-major bg-stock"
          >
            <div className="hidden grid-cols-[minmax(0,13rem)_minmax(0,10rem)_minmax(0,7rem)_auto_minmax(0,9rem)_auto] items-center gap-x-4 rounded-t-xl border-b border-grid-major px-4 py-2.5 sm:grid sm:grid-cols-[minmax(0,13rem)_minmax(0,10rem)_minmax(0,7rem)_auto_minmax(0,9rem)_auto]">
              <span className="legend text-ink-3">Service</span>
              <span className="legend text-ink-3">Owner team</span>
              <span className="legend text-ink-3">Language</span>
              <span className="legend text-ink-3">Threshold</span>
              <span className="legend text-ink-3">Dependencies</span>
              <span className="legend text-ink-3">Blast radius</span>
            </div>

            <ol className="divide-y divide-grid-minor">
              {services.map((svc) => (
                <CatalogRow
                  key={svc.service_id}
                  svc={svc}
                  blastInfo={blast?.get(svc.service_id) ?? null}
                  graphKnown={graphKnown}
                />
              ))}
            </ol>
          </section>
        )}
      </main>
    </div>
  )
}

function CatalogRow({
  svc,
  blastInfo,
  graphKnown,
}: {
  svc: RegistryService
  blastInfo: BlastInfo | null
  graphKnown: boolean
}) {
  const [open, setOpen] = useState(false)
  const deps = blastInfo?.dependents.length ?? null
  const blastCount = blastInfo ? blastInfo.blast.length : null

  const thresholdColor = THRESHOLD_COLOR[svc.alert_threshold] ?? 'var(--color-ink-3)'
  const active = svc.is_active

  return (
    <li className="border-b border-grid-minor last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="grid w-full cursor-pointer grid-cols-[minmax(0,13rem)_minmax(0,10rem)_minmax(0,7rem)_auto_minmax(0,9rem)_auto] items-center gap-x-4 gap-y-1 px-4 py-3.5 text-left transition-colors hover:bg-stock-2 sm:grid-cols-[minmax(0,13rem)_minmax(0,10rem)_minmax(0,7rem)_auto_minmax(0,9rem)_auto]"
      >
        <span className="flex items-center gap-3">
          <span
            className="inline-block h-2 w-2 shrink-0"
            style={{
              backgroundColor: active ? 'var(--color-ink)' : 'var(--color-ink-3)',
              borderRadius: 0,
            }}
            aria-hidden="true"
          />
          <span className="data-tight truncate text-ink">{svc.service_id}</span>
        </span>
        <span className="truncate text-[0.875rem] leading-snug text-ink-2">
          {svc.owner_team}
        </span>
        <span className="truncate text-[0.875rem] leading-snug text-ink-2">
          {svc.language ?? '—'}
        </span>
        <span className="data-tight uppercase" style={{ color: thresholdColor }}>
          {svc.alert_threshold}
        </span>
        <span className="data-tight text-ink-2">
          {graphKnown
            ? deps != null
              ? deps === 0
                ? 'none'
                : `${deps} dependent${deps === 1 ? '' : 's'}`
              : '—'
            : 'unread'}
        </span>
        <span className="flex items-center justify-end gap-2">
          <span className="data-tight text-ink-2">
            {graphKnown
              ? blastCount != null
                ? `${blastCount} affected`
                : '—'
              : 'unread'}
          </span>
          <LeaderArrow
            className={`text-ink-2 transition-transform ${open ? 'rotate-90' : ''}`}
          />
        </span>
      </button>

      {open ? (
        <div className="border-t border-grid-minor bg-stock-2 px-4 py-4">
          <div className="grid gap-x-8 gap-y-3 lg:grid-cols-2">
            <MetaField label="Repository" value={svc.repo} />
            <MetaField label="Architecture" value={svc.architecture_type} />
            <MetaField
              label="Alert threshold"
              value={svc.alert_threshold}
              tone={thresholdColor}
            />
            <MetaField label="Active" value={active ? 'yes' : 'no'} />
          </div>
          <div className="mt-4 grid gap-x-8 gap-y-3 lg:grid-cols-2">
            <MetaList
              label="Services depending on this one"
              items={blastInfo?.dependents ?? null}
              graphKnown={graphKnown}
            />
            <MetaList
              label="Blast radius (transitive dependents)"
              items={blastInfo ? blastInfo.blast : null}
              graphKnown={graphKnown}
            />
          </div>
        </div>
      ) : null}
    </li>
  )
}

function MetaField({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone?: string
}) {
  return (
    <div>
      <dt className="legend text-ink-3">{label}</dt>
      <dd
        className="data-tight mt-1.5 break-words text-ink"
        style={tone ? { color: tone } : undefined}
      >
        {value}
      </dd>
    </div>
  )
}

function MetaList({
  label,
  items,
  graphKnown,
}: {
  label: string
  items: string[] | null
  graphKnown: boolean
}) {
  if (!graphKnown) {
    return (
      <div>
        <dt className="legend text-ink-3">{label}</dt>
        <dd className="mt-1.5 text-[0.875rem] leading-snug text-tentative">
          unread — graph unreachable
        </dd>
      </div>
    )
  }
  if (items == null) {
    return (
      <div>
        <dt className="legend text-ink-3">{label}</dt>
        <dd className="mt-1.5 text-[0.875rem] leading-snug text-ink-2">—</dd>
      </div>
    )
  }
  return (
    <div>
      <dt className="legend text-ink-3">
        {label} · {items.length}
      </dt>
      <dd className="mt-1.5 text-[0.875rem] leading-snug text-ink-2">
        {items.length === 0 ? (
          'none'
        ) : (
          <span className="flex flex-wrap gap-x-3 gap-y-1">
            {items.map((id) => (
              <span key={id} className="data-tight text-ink">
                {id}
              </span>
            ))}
          </span>
        )}
      </dd>
    </div>
  )
}

function Readout({
  label,
  value,
}: {
  label: string
  value: string
}) {
  return (
    <div className="rounded-xl border border-grid-major bg-stock p-4">
      <dt className="legend text-ink-3">{label}</dt>
      <dd className="data-tight mt-2 text-ink">{value}</dd>
    </div>
  )
}

function LoadingRows() {
  return (
    <div className="mt-6 divide-y divide-grid-minor border border-grid-major bg-stock" aria-busy="true" aria-label="Loading service catalog">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="flex items-center gap-4 px-4 py-4">
          <span className="h-2 w-2 animate-pulse bg-grid-major" />
          <span className="h-3 w-32 animate-pulse bg-stock-3" />
          <span className="h-3 w-24 animate-pulse bg-stock-3" />
          <span className="h-3 w-20 animate-pulse bg-stock-3" />
          <span className="h-3 ml-auto w-20 animate-pulse bg-stock-3" />
        </div>
      ))}
    </div>
  )
}