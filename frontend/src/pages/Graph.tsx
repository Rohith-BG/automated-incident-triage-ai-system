import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import BoardMasthead from '../components/BoardMasthead'
import { LeaderArrow } from '../components/Icons'
import { withAuthRetry } from '../lib/auth'
import { useCurrentUser } from '../lib/useCurrentUser'
import {
  fetchActiveGraph,
  fetchKgBootstrapStatus,
  fetchProposals,
  type KgBootstrapStatus,
  type KgSnapshot,
} from '../data/kg'
import {
  fetchNotifications,
  type NotificationsSummary,
} from '../data/notifications'

type LoadState = 'loading' | 'ready'

interface HubData {
  status: KgBootstrapStatus | null
  graph: KgSnapshot | null
  pendingCount: number | null
  notifications: NotificationsSummary | null
}

export default function Graph() {
  const currentUser = useCurrentUser()
  const isAdmin = currentUser?.role === 'admin'
  const [data, setData] = useState<HubData>({
    status: null,
    graph: null,
    pendingCount: null,
    notifications: null,
  })
  const [state, setState] = useState<LoadState>('loading')
  const [notificationsNote, setNotificationsNote] = useState<string | null>(null)

  const load = useCallback(async (): Promise<void> => {
    try {
      const [status, graph, proposals, notificationsResult] =
        await Promise.allSettled([
          withAuthRetry(() => fetchKgBootstrapStatus()),
          withAuthRetry(() => fetchActiveGraph()),
          withAuthRetry(() => fetchProposals()),
          withAuthRetry(() => fetchNotifications()),
        ])

      setData({
        status:
          status.status === 'fulfilled' ? status.value : null,
        graph: graph.status === 'fulfilled' ? graph.value : null,
        pendingCount:
          proposals.status === 'fulfilled'
            ? proposals.value.filter((p) => p.status === 'pending').length
            : null,
        notifications:
          notificationsResult.status === 'fulfilled'
            ? notificationsResult.value
            : null,
      })

      if (proposals.status === 'rejected') {
        setNotificationsNote(
          'The review queue could not be read — counts are reported unread.',
        )
      }
      if (
        notificationsResult.status === 'rejected' &&
        notificationsResult.reason instanceof Error
      ) {
        setNotificationsNote(
          'Sign in to read the notification stream for build and review events.',
        )
      }
      setState('ready')
    } catch {
      setState('loading')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const nodes = data.graph?.nodes.length ?? null
  const edges = data.graph?.edges.length ?? null
  const pendingCount = data.pendingCount
  const unread = data.notifications?.unread ?? null

  return (
    <div className="min-h-dvh bg-stock">
      <BoardMasthead />

      <main className="mx-auto w-full max-w-[1400px] px-5 py-10 sm:px-8 lg:px-12">
        <header className="mb-8">
          <h1 className="verdict-type text-[clamp(2rem,4.5vw,3.25rem)]">
            Knowledge graph
          </h1>
          <p className="mt-3 max-w-full text-[1.0625rem] leading-[1.6] text-ink-2">
            The knowledge graph maps every service and the relationships between
            them: dependencies, ownership, and blast radius. Explore the
            live graph or run a build to discover new relationships, then
            review and approve them.
          </p>
        </header>

        {/* ── Status readout: the instrument reporting on itself ── */}
        <section aria-label="Knowledge graph status" className="mt-8">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Readout
              label="Active graph"
              value={
                state === 'ready' && data.status
                  ? data.status.has_active_graph
                    ? 'present'
                    : 'empty'
                  : 'reading…'
              }
            />
            <Readout
              label="Topology"
              value={
                nodes != null && edges != null
                  ? `${nodes} nodes · ${edges} edges`
                  : 'reading…'
              }
            />
            {isAdmin && (
              <Readout
                label="Under review"
                value={
                  pendingCount != null
                    ? `${pendingCount} proposal${pendingCount === 1 ? '' : 's'}`
                    : nodes != null
                      ? '0 proposals'
                      : 'reading…'
                }
              />
            )}
            <Readout
              label="Notifications"
              value={
                unread != null
                  ? `${unread} unread`
                  : notificationsNote
                    ? 'sign-in required'
                    : 'reading…'
              }
            />
          </div>
          {notificationsNote ? (
            <p className="mt-2 text-[0.8125rem] leading-snug text-ink-3">
              {notificationsNote}
            </p>
          ) : null}
        </section>

        {/* ── Index cards: where the work happens ── */}
        <section aria-label="Knowledge graph actions" className={`mt-10 grid gap-4 ${isAdmin ? 'sm:grid-cols-2' : 'sm:grid-cols-1 max-w-[42rem]'}`}>
          <Link
            to="/graph/topology"
            className="group flex flex-col rounded-xl border border-grid-major bg-stock p-5 transition-colors hover:border-ink"
          >
            <div className="flex items-start justify-between">
              <span className="font-display text-ink" aria-hidden="true">
                ⬢
              </span>
              <span className="legend text-ink-2 transition-colors group-hover:text-signal">
                {nodes != null && edges != null
                  ? `${nodes} nodes · ${edges} edges`
                  : 'reading…'}
              </span>
            </div>
            <h2 className="section-type mt-auto flex items-baseline gap-2 pt-6 text-[1.35rem]">
              Graph view
              <LeaderArrow className="text-signal opacity-0 transition-opacity group-hover:opacity-100" />
            </h2>
            <p className="mt-2.5 text-[0.875rem] leading-relaxed text-ink-2">
              The active graph as it stands — every approved relationship
              drawn as rings and ruled edges, with the blast radius lit on
              hover.
            </p>
          </Link>

          {isAdmin && (
            <Link
              to="/graph/build"
              className="group flex flex-col rounded-xl border border-grid-major bg-stock p-5 transition-colors hover:border-ink"
            >
              <div className="flex items-start justify-between">
                <span className="font-display text-ink" aria-hidden="true">
                  ◇
                </span>
                <span className="legend text-ink-2 transition-colors group-hover:text-signal">
                  {pendingCount != null
                    ? `${pendingCount} pending`
                    : 'reading…'}
                </span>
              </div>
              <h2 className="section-type mt-auto flex items-baseline gap-2 pt-6 text-[1.35rem]">
                Build KG
                <LeaderArrow className="text-signal opacity-0 transition-opacity group-hover:opacity-100" />
              </h2>
              <p className="mt-2.5 text-[0.875rem] leading-relaxed text-ink-2">
                Run a build from a repository or fixture, then review what the
                agent discovered. Approve lands it in the graph; feedback sends
                the proposal back for revision.
              </p>
            </Link>
          )}
        </section>
      </main>
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