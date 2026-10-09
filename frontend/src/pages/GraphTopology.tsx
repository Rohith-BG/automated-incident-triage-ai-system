import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import BoardMasthead from '../components/BoardMasthead'
import KgBloom from '../components/KgBloom'
import { withAuthRetry } from '../lib/auth'
import { ApiError } from '../lib/api'
import { fetchActiveGraph, type KgSnapshot } from '../data/kg'

type LoadState = 'loading' | 'ready'
type UnreachableReason = 'auth' | 'offline'

export default function GraphTopology() {
  const [graph, setGraph] = useState<KgSnapshot | null>(null)
  const [state, setState] = useState<LoadState>('loading')
  const [unreachableReason, setUnreachableReason] =
    useState<UnreachableReason | null>(null)
  const [enlarged, setEnlarged] = useState(false)

  const load = useCallback(async (): Promise<void> => {
    try {
      const result = await withAuthRetry(() => fetchActiveGraph())
      setGraph(result)
      setUnreachableReason(null)
    } catch (err) {
      setGraph(null)
      setUnreachableReason(
        err instanceof ApiError && err.status === 401 ? 'auth' : 'offline',
      )
    }
    setState('ready')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    const onKey = (event: KeyboardEvent): void => {
      if (event.key === 'Escape') setEnlarged(false)
    }
    if (enlarged) window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [enlarged])

  const nodes = graph?.nodes.length ?? 0
  const edges = graph?.edges.length ?? 0
  const empty = graph != null && nodes === 0

  const GraphViewport = state === 'loading' ? (
    <div className="flex h-full w-full items-center justify-center" style={{ background: '#0f1117' }}>
      <div className="flex flex-col items-center gap-3">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-transparent"
             style={{ borderTopColor: '#5b8af5', borderRightColor: '#5b8af5' }} />
        <span style={{ color: '#6b7894', fontSize: '0.8125rem' }}>Loading graph…</span>
      </div>
    </div>
  ) : graph == null ? (
    <div
      className="flex h-full w-full flex-col items-center justify-center px-6 text-center"
      style={{ background: '#0f1117' }}
    >
      <p style={{ color: '#e8edf5', fontSize: '1.125rem', fontWeight: 600 }}>
        Graph unreachable
      </p>
      <p style={{ color: '#6b7894', fontSize: '0.875rem', maxWidth: '28rem', marginTop: '8px', lineHeight: 1.6 }}>
        {unreachableReason === 'auth'
          ? 'Sign in to read the active knowledge graph.'
          : 'Could not reach the graph service. Check that the backend is running, then retry.'}
      </p>
      <button
        type="button"
        onClick={() => {
          setState('loading')
          void load()
        }}
        style={{
          marginTop: '16px',
          padding: '8px 20px',
          background: 'rgba(91,138,245,0.15)',
          border: '1px solid rgba(91,138,245,0.3)',
          borderRadius: '8px',
          color: '#5b8af5',
          cursor: 'pointer',
          fontSize: '0.8125rem',
          fontWeight: 600,
        }}
      >
        Retry
      </button>
    </div>
  ) : empty ? (
    <div
      className="flex h-full w-full flex-col items-center justify-center px-6 text-center"
      style={{ background: '#0f1117' }}
    >
      <p style={{ color: '#e8edf5', fontSize: '1.125rem', fontWeight: 600 }}>
        No approved graph yet
      </p>
      <p style={{ color: '#6b7894', fontSize: '0.875rem', maxWidth: '28rem', marginTop: '8px', lineHeight: 1.6 }}>
        Run a build and approve a proposal to populate the graph.
      </p>
      <Link
        to="/graph/build"
        style={{
          marginTop: '16px',
          padding: '8px 20px',
          background: 'rgba(91,138,245,0.15)',
          border: '1px solid rgba(91,138,245,0.3)',
          borderRadius: '8px',
          color: '#5b8af5',
          textDecoration: 'none',
          fontSize: '0.8125rem',
          fontWeight: 600,
        }}
      >
        Build KG →
      </Link>
    </div>
  ) : (
    <KgBloom snapshot={graph} />
  )

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

        <header className="mt-6 mb-4">
          <div className="flex flex-wrap items-baseline justify-between gap-4">
            <h1 className="verdict-type text-[clamp(2rem,4.5vw,3.25rem)]">
              Graph view
            </h1>
            {graph != null && nodes > 0 && !enlarged && (
              <button
                type="button"
                onClick={() => setEnlarged(true)}
                className="legend cursor-pointer border border-grid-major px-3 py-1.5 text-ink-2 transition-colors hover:border-ink hover:text-ink"
                style={{ borderRadius: '6px' }}
              >
                Fullscreen
              </button>
            )}
          </div>
          <p className="mt-3 max-w-full text-[0.9375rem] leading-[1.6] text-ink-2">
            Interactive knowledge graph — scroll to zoom, drag to pan,
            hover for blast radius, click for details.
          </p>
        </header>

        {/* ── The graph console ── */}
        <section
          aria-label="Graph console"
          className="overflow-hidden"
          style={{ borderRadius: '0.75rem', height: 'calc(100vh - 240px)', minHeight: '500px' }}
        >
          {GraphViewport}
        </section>
      </main>

      {/* ── Fullscreen overlay ── */}
      {enlarged && graph != null && nodes > 0 && (
        <div
          role="region"
          aria-label="Graph console, fullscreen"
          className="fixed inset-0 z-50 flex flex-col"
          style={{ background: '#0f1117' }}
        >
          <div
            className="flex items-center justify-between px-5 py-3"
            style={{ borderBottom: '1px solid #2a2f3d' }}
          >
            <div className="flex items-center gap-4">
              <span style={{ color: '#6b7894', fontSize: '0.6875rem', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Graph console
              </span>
              <span style={{ color: '#c8d0e0', fontSize: '0.8125rem' }}>
                {nodes} nodes · {edges} edges
              </span>
            </div>
            <button
              type="button"
              onClick={() => setEnlarged(false)}
              style={{
                padding: '6px 16px',
                background: 'rgba(42,47,61,0.8)',
                border: '1px solid #2a2f3d',
                borderRadius: '8px',
                color: '#c8d0e0',
                cursor: 'pointer',
                fontSize: '0.8125rem',
              }}
            >
              Exit fullscreen
            </button>
          </div>
          <div className="min-h-0 flex-1">
            <KgBloom snapshot={graph} />
          </div>
        </div>
      )}
    </div>
  )
}