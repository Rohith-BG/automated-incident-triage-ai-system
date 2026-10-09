import { useEffect, useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import BoardMasthead from '../components/BoardMasthead'
import KgBloom, { type BloomNodeClickEvent } from '../components/KgBloom'
import { ApiError } from '../lib/api'
import { withAuthRetry } from '../lib/auth'
import { useCurrentUser } from '../lib/useCurrentUser'
import {
  approveProposal,
  fetchKgBootstrapStatus,
  fetchProposals,
  fetchStagingGraph,
  proposalToSnapshot,
  rejectProposal,
  startBootstrap,
  submitProposalFeedback,
  type KgBootstrapStatus,
  type KGProposal,
  type KgSnapshot,
} from '../data/kg'

type LoadState = 'loading' | 'ready'
type RunState = 'idle' | 'running' | 'done' | 'error'

function formatTimestamp(value: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

export default function GraphBuild() {
  const currentUser = useCurrentUser()

  // Still loading the user — render nothing to avoid a layout flash
  if (currentUser === undefined) return null
  // Non-admin users cannot access Build KG — send them back to the hub
  if (currentUser === null || currentUser.role !== 'admin') {
    return <Navigate to="/graph" replace />
  }

  return <GraphBuildInner />
}

function GraphBuildInner() {
  const [status, setStatus] = useState<KgBootstrapStatus | null>(null)
  const [pending, setPending] = useState<KGProposal[]>([])
  const [past, setPast] = useState<KGProposal[]>([])
  const [stagingGraph, setStagingGraph] = useState<KgSnapshot | null>(null)
  const [selectedNodes, setSelectedNodes] = useState<
    Record<string, BloomNodeClickEvent | null>
  >({})
  const [submittingAction, setSubmittingAction] = useState<
    Record<string, string | null>
  >({})
  const [pastGraphOpen, setPastGraphOpen] = useState<Record<string, boolean>>({})

  const [loadState, setLoadState] = useState<LoadState>('loading')
  const [authNote, setAuthNote] = useState<string | null>(null)
  const [reviewError, setReviewError] = useState<string | null>(null)
  const [runState, setRunState] = useState<RunState>('idle')
  const [runError, setRunError] = useState<string | null>(null)
  const [feedback, setFeedback] = useState<Record<string, string>>({})

  const reload = async (): Promise<void> => {
    const [
      statusResult,
      pendingResult,
      approvedResult,
      rejectedResult,
      stagingResult,
    ] = await Promise.allSettled([
      withAuthRetry(() => fetchKgBootstrapStatus()),
      withAuthRetry(() => fetchProposals('pending')),
      withAuthRetry(() => fetchProposals('approved')),
      withAuthRetry(() => fetchProposals('rejected')),
      withAuthRetry(() => fetchStagingGraph()),
    ])
    const listResults = [pendingResult, approvedResult, rejectedResult]
    if (statusResult.status === 'fulfilled') setStatus(statusResult.value)
    if (pendingResult.status === 'fulfilled') setPending(pendingResult.value)
    if (stagingResult.status === 'fulfilled') setStagingGraph(stagingResult.value)
    if (
      approvedResult.status === 'fulfilled' &&
      rejectedResult.status === 'fulfilled'
    ) {
      setPast([...approvedResult.value, ...rejectedResult.value])
    }
    const failed = listResults.find((result) => result.status === 'rejected')
    if (failed && failed.status === 'rejected') {
      const reason = failed.reason
      if (
        reason instanceof ApiError &&
        (reason.status === 401 || reason.status === 403)
      ) {
        setAuthNote(
          'Build, approve, and feedback are admin actions — sign in with an operator or admin role to act on proposals.',
        )
      } else {
        setReviewError('The review queue could not be read.')
      }
    }
    setLoadState('ready')
  }

  useEffect(() => {
    reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleNodeClick = (proposalId: string, node: BloomNodeClickEvent) => {
    setSelectedNodes((prev) => ({ ...prev, [proposalId]: node }))
    setFeedback((prev) => {
      const current = prev[proposalId] ?? ''
      if (current.includes(node.id)) return prev
      const prefix = `[Node: ${node.id}]`
      if (!current.trim()) return { ...prev, [proposalId]: `${prefix} ` }
      return { ...prev, [proposalId]: `${current.trim()} ${prefix} ` }
    })
  }

  const handleAttachNode = (proposalId: string, nodeId: string) => {
    setFeedback((prev) => {
      const current = prev[proposalId] ?? ''
      if (current.includes(nodeId)) return prev
      const prefix = `[Node: ${nodeId}]`
      if (!current.trim()) return { ...prev, [proposalId]: `${prefix} ` }
      return { ...prev, [proposalId]: `${current.trim()} ${prefix} ` }
    })
  }

  const applyTemplate = (proposalId: string, text: string) => {
    setFeedback((prev) => ({
      ...prev,
      [proposalId]: text,
    }))
  }

  const clearSelectedNode = (proposalId: string) => {
    setSelectedNodes((prev) => ({ ...prev, [proposalId]: null }))
  }

  const onRun = async (): Promise<void> => {
    setRunState('running')
    setRunError(null)
    try {
      await withAuthRetry(() => startBootstrap({}))
      setRunState('done')
      await reload()
    } catch (err) {
      setRunState('error')
      setRunError(
        err instanceof ApiError && err.status === 401
          ? 'Sign in with an admin role to run a build.'
          : 'The build could not start — the source may be unreachable.',
      )
    }
  }

  const guardAction = (err: unknown, fallback: string): void => {
    setReviewError(
      err instanceof ApiError && (err.status === 401 || err.status === 403)
        ? 'Sign in with an admin role to review proposals.'
        : fallback,
    )
  }

  const onApprove = async (id: string): Promise<void> => {
    setReviewError(null)
    setSubmittingAction((prev) => ({ ...prev, [id]: 'approve' }))
    try {
      await withAuthRetry(() => approveProposal(id))
      await reload()
    } catch (err) {
      guardAction(err, 'The proposal could not be approved.')
    } finally {
      setSubmittingAction((prev) => ({ ...prev, [id]: null }))
    }
  }

  const onReject = async (id: string): Promise<void> => {
    setReviewError(null)
    setSubmittingAction((prev) => ({ ...prev, [id]: 'reject' }))
    try {
      await withAuthRetry(() => rejectProposal(id, feedback[id]))
      await reload()
    } catch (err) {
      guardAction(err, 'The proposal could not be rejected.')
    } finally {
      setSubmittingAction((prev) => ({ ...prev, [id]: null }))
    }
  }

  const onFeedback = async (id: string): Promise<void> => {
    setReviewError(null)
    setSubmittingAction((prev) => ({ ...prev, [id]: 'feedback' }))
    try {
      await withAuthRetry(() => submitProposalFeedback(id, feedback[id] ?? ''))
      await reload()
    } catch (err) {
      guardAction(err, 'The feedback could not be submitted.')
    } finally {
      setSubmittingAction((prev) => ({ ...prev, [id]: null }))
    }
  }

  return (
    <div className="min-h-dvh bg-stock">
      <BoardMasthead />

      <main className="mx-auto w-full max-w-[1400px] px-5 py-10 sm:px-8 lg:px-12">
        <Link
          to="/graph"
          className="legend inline-flex items-center gap-2 text-ink-2 no-underline transition-colors hover:text-ink"
          aria-label="Back to knowledge graph"
        >
          ← Knowledge graph
        </Link>

        <header className="mt-6 mb-8">
          <h1 className="verdict-type text-[clamp(2rem,4.5vw,3.25rem)]">
            Build KG
          </h1>
          <p className="mt-3 max-w-full text-[1.0625rem] leading-[1.6] text-ink-2">
            Build KG turns a repository or a service fixture into a knowledge
            graph for the platform. Run a build, read what the agent
            discovered, and approve the relationships you trust or send them
            back with feedback. Nothing reaches the live graph until you make a
            decision.
          </p>
        </header>

        {/* ── Build instrument ── */}
        <section
          aria-label="Graph build instrument"
          className="overflow-hidden rounded-xl border border-grid-major bg-stock"
        >
          <div className="border-b border-grid-major px-6 py-4 flex flex-wrap items-center justify-between gap-4">
            <div>
              <h2 className="text-[1.05rem] font-semibold text-ink">
                Run a build
              </h2>
              <p className="mt-1 text-[0.8125rem] text-ink-3">
                Parameters loaded from environment configuration (.env)
              </p>
            </div>
            <span className="legend rounded-md bg-stock-2 px-2.5 py-1 text-ink-2 border border-grid-major font-mono text-[0.8125rem]">
              Source: {status?.source ?? 'github_repo'}
            </span>
          </div>

          <div className="grid gap-0 lg:grid-cols-[1fr_minmax(18rem,20rem)]">
            <div className="p-6 flex flex-col justify-between">
              <div>
                <p className="text-[0.9375rem] leading-relaxed text-ink-2">
                  The knowledge graph bootstrap agent reads repository intelligence and discovers services, dependencies, and ownership automatically using the environment configuration. No manual parameters required.
                </p>

                <div className="mt-5 grid gap-3 sm:grid-cols-2">
                  <div className="rounded-lg border border-grid-major bg-stock-2 p-3.5">
                    <span className="legend block text-ink-3 text-[0.75rem] uppercase tracking-wider">
                      Target Repository / Source
                    </span>
                    <span
                      className="mt-1 block font-mono text-[0.875rem] text-ink font-medium truncate"
                      title={status?.repo || status?.org || 'Configured via .env'}
                    >
                      {status?.repo || status?.org || 'Configured in .env'}
                    </span>
                  </div>

                  <div className="rounded-lg border border-grid-major bg-stock-2 p-3.5">
                    <span className="legend block text-ink-3 text-[0.75rem] uppercase tracking-wider">
                      Architecture Type
                    </span>
                    <span className="mt-1 block text-[0.875rem] text-ink font-medium capitalize">
                      {status?.architecture_type ?? 'monolith'}
                    </span>
                  </div>

                  <div className="rounded-lg border border-grid-major bg-stock-2 p-3.5">
                    <span className="legend block text-ink-3 text-[0.75rem] uppercase tracking-wider">
                      Bootstrap Source
                    </span>
                    <span className="mt-1 block text-[0.875rem] text-ink font-medium capitalize">
                      {status?.source?.replace('_', ' ') ?? 'github repo'}
                    </span>
                  </div>

                  <div className="rounded-lg border border-grid-major bg-stock-2 p-3.5">
                    <span className="legend block text-ink-3 text-[0.75rem] uppercase tracking-wider">
                      Owner Team
                    </span>
                    <span className="mt-1 block text-[0.875rem] text-ink font-medium">
                      {status?.owner_team ?? 'platform-team'}
                    </span>
                  </div>
                </div>
              </div>

              <div className="mt-6 pt-5 border-t border-grid-major flex flex-wrap items-center gap-4">
                <button
                  type="button"
                  onClick={() => void onRun()}
                  className="action-primary-stock cursor-pointer"
                  disabled={runState === 'running'}
                >
                  {runState === 'running' ? 'Building…' : 'Run build'}
                </button>
                {runState === 'done' ? (
                  <span className="legend text-ink-2">
                    Build dispatched — review the proposals below.
                  </span>
                ) : null}
                {runError ? (
                  <span className="legend text-tentative">{runError}</span>
                ) : null}
              </div>
            </div>

            <div className="border-t border-grid-major px-6 py-6 lg:border-t-0 lg:border-l">
              <h3 className="legend mb-3 text-ink-3">Antenna state</h3>
              {loadState === 'loading' ? (
                <div className="space-y-3 py-1">
                  <div className="h-3 w-3/4 animate-pulse bg-grid-major" />
                  <div className="h-3 w-1/2 animate-pulse bg-grid-major" />
                  <div className="h-3 w-2/3 animate-pulse bg-grid-major" />
                </div>
              ) : (
                <dl className="divide-y divide-grid-major">
                  <StatusRow
                    label="Active graph"
                    value={status?.has_active_graph ? 'present' : 'empty'}
                  />
                  <StatusRow label="Pending" value={String(status?.pending_count ?? '—')} />
                  <StatusRow
                    label="Needs bootstrap"
                    value={status?.needs_bootstrap ? 'yes' : 'no'}
                  />
                  <StatusRow
                    label="Bootstrap enabled"
                    value={status?.bootstrap_enabled ? 'enabled' : 'off'}
                  />
                </dl>
              )}
              {authNote ? (
                <p className="mt-4 text-[0.8125rem] leading-snug text-ink-3">
                  {authNote}
                </p>
              ) : null}
            </div>
          </div>
        </section>

        {/* ── Review queue: the human in the loop ── */}
        <section aria-label="Review queue" className="mt-10 mb-8">
          <div className="mb-4 flex items-baseline gap-3">
            <h2 className="section-type text-[1.35rem]">Under review</h2>
            <span className="legend text-ink-3">
              {pending.length} pending · decision required before anything
              reaches the graph
            </span>
          </div>

          {reviewError ? (
            <p className="mb-4 rounded-lg border border-grid-major bg-white p-4 text-[0.9375rem] text-tentative">
              {reviewError}
            </p>
          ) : null}

          {loadState === 'loading' ? (
            <div className="rounded-xl border border-grid-major bg-white p-6">
              <div className="h-3 w-full animate-pulse bg-stock-3" />
              <div className="mt-3 h-3 w-2/3 animate-pulse bg-stock-3" />
            </div>
          ) : pending.length === 0 ? (
            <div className="overflow-hidden rounded-xl border border-grid-major bg-white px-6 py-10 text-center shadow-xs">
              <p className="section-type text-ink">Nothing on the bench</p>
              <p className="mx-auto mt-2 max-w-full text-[0.9375rem] leading-relaxed text-ink-2">
                No proposals are waiting. Run a build above and the agent's
                discoveries will land here for your decision.
              </p>
            </div>
          ) : (
            <ul className="space-y-6">
              {pending.map((proposal) => {
                const proposalSnapshot = (() => {
                  const fromMutations = proposalToSnapshot(proposal)
                  if (fromMutations.nodes.length > 0) return fromMutations
                  if (stagingGraph && stagingGraph.nodes.length > 0) return stagingGraph
                  return { nodes: [], edges: [] }
                })()

                const selectedNode = selectedNodes[proposal.id]
                const action = submittingAction[proposal.id]

                return (
                  <li
                    key={proposal.id}
                    className="overflow-hidden rounded-xl border border-grid-major bg-white p-6 sm:p-7 space-y-6 shadow-xs"
                  >
                    {/* Header */}
                    <div className="flex flex-wrap items-baseline gap-x-4 gap-y-2">
                      <div>
                        <h3 className="section-type text-[1.15rem] font-semibold text-ink">
                          {proposal.service_id}
                        </h3>
                        <span className="data-tight text-ink-3">
                          {proposal.repo} · {proposal.architecture_type}
                        </span>
                      </div>
                      <span className="legend ml-auto rounded-full border border-tentative/30 bg-tentative/10 px-2.5 py-1 text-xs font-semibold uppercase tracking-wide text-tentative">
                        awaiting decision
                      </span>
                    </div>

                    <p className="max-w-full text-[0.9375rem] leading-relaxed text-ink-2">
                      {proposal.diff_summary}
                    </p>

                    {/* Staged Knowledge Graph Preview - retains dark Bloom canvas chassis */}
                    <div className="overflow-hidden rounded-xl border border-grid-major bg-[#0f1117]">
                      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#242b38] bg-[#141721] px-4 py-2.5">
                        <div className="flex items-center gap-2">
                          <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
                          <span className="text-xs font-semibold uppercase tracking-wider text-[#e8ede6]">
                            Staged Knowledge Graph ({proposalSnapshot.nodes.length} nodes · {proposalSnapshot.edges.length} edges)
                          </span>
                        </div>
                        <span className="text-[0.75rem] text-[#93a094]">
                          Click any node to inspect & attach it to your correction feedback
                        </span>
                      </div>

                      {proposalSnapshot.nodes.length > 0 ? (
                        <div className="h-[460px] w-full">
                          <KgBloom
                            snapshot={proposalSnapshot}
                            height="460px"
                            selectedNodeId={selectedNode?.id ?? null}
                            onNodeClick={(n) => handleNodeClick(proposal.id, n)}
                            onAttachFeedback={(nodeId) => handleAttachNode(proposal.id, nodeId)}
                            attachButtonLabel="Attach node to feedback"
                          />
                        </div>
                      ) : (
                        <div className="p-8 text-center text-sm text-[#93a094]">
                          No nodes found for this staged proposal.
                        </div>
                      )}
                    </div>

                    {/* Review Feedback & Decision Controls - plain white background */}
                    <div className="space-y-4">
                      {selectedNode ? (
                        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-grid-major bg-stock-2/60 p-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="legend text-ink-3">Target node:</span>
                            <span className="rounded border border-grid-major bg-white px-2 py-0.5 font-mono text-xs font-bold text-ink">
                              {selectedNode.id}
                            </span>
                            <span className="rounded border border-grid-major bg-white px-1.5 py-0.5 font-mono text-[0.6875rem] uppercase text-ink-2">
                              {selectedNode.kind}
                            </span>
                            {selectedNode.owner && (
                              <span className="legend text-ink-3">
                                owner: {selectedNode.owner}
                              </span>
                            )}
                          </div>

                          <div className="flex flex-wrap items-center gap-1.5">
                            <span className="legend mr-1 text-ink-3">Quick templates:</span>
                            <button
                              type="button"
                              onClick={() =>
                                applyTemplate(
                                  proposal.id,
                                  `Remove node "${selectedNode.id}" — not an active service`,
                                )
                              }
                              className="legend cursor-pointer rounded border border-grid-major bg-white px-2.5 py-1 text-ink-2 transition-colors hover:border-ink hover:text-ink"
                            >
                              Remove node
                            </button>
                            <button
                              type="button"
                              onClick={() =>
                                applyTemplate(
                                  proposal.id,
                                  `Remove incorrect dependency: "${selectedNode.id}" should not depend on `,
                                )
                              }
                              className="legend cursor-pointer rounded border border-grid-major bg-white px-2.5 py-1 text-ink-2 transition-colors hover:border-ink hover:text-ink"
                            >
                              Wrong dependency
                            </button>
                            <button
                              type="button"
                              onClick={() =>
                                applyTemplate(
                                  proposal.id,
                                  `Reclassify "${selectedNode.id}" as module instead of service`,
                                )
                              }
                              className="legend cursor-pointer rounded border border-grid-major bg-white px-2.5 py-1 text-ink-2 transition-colors hover:border-ink hover:text-ink"
                            >
                              Misclassified
                            </button>
                            <button
                              type="button"
                              onClick={() => clearSelectedNode(proposal.id)}
                              className="legend ml-1 cursor-pointer px-1.5 py-0.5 text-ink-3 hover:text-ink"
                              title="Deselect node"
                            >
                              ✕
                            </button>
                          </div>
                        </div>
                      ) : (
                        <p className="legend text-[0.8125rem] text-ink-3">
                          Tip: Click any node in the graph above to target it for correction and attach its name to your feedback.
                        </p>
                      )}

                      {/* Aligned Decision & Feedback Action Bar */}
                      <div className="flex flex-wrap items-center gap-3 pt-1">
                        <button
                          type="button"
                          className="action-primary cursor-pointer whitespace-nowrap rounded-lg"
                          disabled={Boolean(action)}
                          onClick={() => void onApprove(proposal.id)}
                        >
                          {action === 'approve' ? 'Approving…' : 'Approve'}
                        </button>

                        <button
                          type="button"
                          className="action-primary-stock cursor-pointer whitespace-nowrap rounded-lg"
                          disabled={Boolean(action)}
                          onClick={() => void onReject(proposal.id)}
                        >
                          {action === 'reject' ? 'Rejecting…' : 'Reject'}
                        </button>

                        <div className="flex min-w-[280px] flex-1 items-center gap-2">
                          <input
                            type="text"
                            value={feedback[proposal.id] ?? ''}
                            onChange={(event) =>
                              setFeedback((current) => ({
                                ...current,
                                [proposal.id]: event.target.value,
                              }))
                            }
                            placeholder={
                              selectedNode
                                ? `Feedback for "${selectedNode.id}" (e.g. remove dependency, update owner)…`
                                : 'Reason or revision notes for misleading nodes / dependencies…'
                            }
                            className="flex-1 rounded-lg border border-grid-major bg-white px-3.5 py-[0.7rem] text-[0.875rem] text-ink placeholder:text-ink-3 outline-none transition-colors focus:border-ink"
                          />

                          <button
                            type="button"
                            className="action-primary-stock cursor-pointer whitespace-nowrap rounded-lg disabled:cursor-not-allowed disabled:opacity-40"
                            disabled={!(feedback[proposal.id] ?? '').trim() || Boolean(action)}
                            onClick={() => void onFeedback(proposal.id)}
                          >
                            {action === 'feedback' ? 'Submitting…' : 'Send feedback'}
                          </button>
                        </div>
                      </div>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </section>

        {/* ── Past reviews: decisions already on record ── */}
        <section aria-label="Past reviews" className="pb-8">
          <div className="mb-4 flex items-baseline gap-3">
            <h2 className="section-type text-[1.35rem]">Past reviews</h2>
            <span className="legend text-ink-3">
              {past.length} decision{`${past.length === 1 ? '' : 's'}`} on
              record from the review queue
            </span>
          </div>

          {past.length === 0 ? (
            <div className="overflow-hidden rounded-xl border border-grid-major bg-white px-6 py-10 text-center">
              <p className="section-type text-ink">No decisions yet</p>
              <p className="mx-auto mt-2 max-w-full text-[0.9375rem] leading-relaxed text-ink-2">
                Approvals and rejections will appear here as you review
                proposals.
              </p>
            </div>
          ) : (
            <ul className="space-y-4">
              {past.map((proposal) => {
                const pastSnapshot = proposalToSnapshot(proposal)
                const isOpen = pastGraphOpen[proposal.id]

                return (
                  <li
                    key={proposal.id}
                    className="overflow-hidden rounded-xl border border-grid-major bg-white p-5 sm:p-6 space-y-3 shadow-xs"
                  >
                    <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
                      <h3 className="section-type text-[1.05rem] text-ink font-semibold">
                        {proposal.service_id}
                      </h3>
                      <span className="data-tight text-ink-3">
                        {proposal.repo} · {proposal.architecture_type}
                      </span>
                      <span
                        className={`legend ml-auto px-2 py-0.5 rounded text-xs font-medium ${
                          proposal.status === 'approved'
                            ? 'bg-stock-2 text-ink-2 border border-grid-major'
                            : 'bg-tentative/10 text-tentative border border-tentative/30'
                        }`}
                      >
                        {proposal.status}
                      </span>
                    </div>
                    {proposal.reviewed_at ? (
                      <p className="text-[0.8125rem] leading-snug text-ink-3">
                        Reviewed {formatTimestamp(proposal.reviewed_at)}
                        {proposal.reviewed_by
                          ? ` by ${proposal.reviewed_by}`
                          : ''}
                      </p>
                    ) : null}
                    <p className="max-w-full text-[0.9375rem] leading-relaxed text-ink-2">
                      {proposal.diff_summary}
                    </p>
                    {proposal.admin_feedback ? (
                      <p className="text-[0.8125rem] leading-snug text-tentative bg-tentative/5 p-2.5 rounded border border-tentative/20">
                        Feedback: {proposal.admin_feedback}
                      </p>
                    ) : null}

                    {pastSnapshot.nodes.length > 0 && (
                      <div className="pt-2">
                        <button
                          type="button"
                          onClick={() =>
                            setPastGraphOpen((prev) => ({
                              ...prev,
                              [proposal.id]: !prev[proposal.id],
                            }))
                          }
                          className="legend text-xs px-2.5 py-1 rounded border border-grid-major text-ink-2 hover:text-ink hover:bg-stock-2 transition-colors cursor-pointer"
                        >
                          {isOpen ? '▲ Hide proposal graph' : '▼ Inspect proposal graph'}
                        </button>
                        {isOpen && (
                          <div className="mt-3 h-[320px] w-full rounded-lg border border-grid-major overflow-hidden">
                            <KgBloom snapshot={pastSnapshot} height="320px" />
                          </div>
                        )}
                      </div>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </section>
      </main>
    </div>
  )
}

function StatusRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-3">
      <dt className="legend text-ink-3">{label}</dt>
      <dd className="data-tight text-ink">{value}</dd>
    </div>
  )
}