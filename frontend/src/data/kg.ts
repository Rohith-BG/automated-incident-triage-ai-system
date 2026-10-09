/**
 * Knowledge-graph domain types and API calls.
 *
 * Types mirror the backend Pydantic response schemas exactly:
 *   - backend/app/schemas/kg_bootstrap.py  (KgBootstrapStatusResponse,
 *     KgStagingSnapshotResponse, KgNode, KgEdge)
 *   - backend/app/schemas/kg_change_proposal.py (KGProposalResponse)
 * All data is read from the live API. When a source is unreachable or a graph
 * is empty, the caller renders an explicit unread state — nothing is invented.
 */

import { api } from '../lib/api'

/* ── Graph snapshot (backend kg_bootstrap schemas) ───────────────────── */

export interface KgNode {
  id: string
  kind: string
  properties: Record<string, unknown>
}

export interface KgEdge {
  from: string
  to: string
  type: string
  evidence: string
}

export interface KgSnapshot {
  nodes: KgNode[]
  edges: KgEdge[]
}

export interface KgBootstrapStatus {
  needs_bootstrap: boolean
  has_active_graph: boolean
  bootstrap_enabled: boolean
  pending_proposal_id: string | null
  approved_proposal_id: string | null
  pending_count: number
  source?: BootstrapSource | string
  repo?: string | null
  org?: string | null
  architecture_type?: string | null
  owner_team?: string | null
}

/* ── KG change proposals (backend kg_change_proposal schema) ─────────── */

export interface KGProposal {
  id: string
  service_id: string
  commit_sha: string
  repo: string
  architecture_type: string
  component_id: string
  proposed_changes: Array<Record<string, unknown>>
  diff_summary: string
  status: string
  admin_feedback: string | null
  parent_proposal_id: string | null
  reviewed_by: string | null
  reviewed_at: string | null
  created_at: string
}

/* ── Node property accessors ─────────────────────────────────────────── */

function prop(node: KgNode, key: string): string | null {
  const value = node.properties[key]
  return typeof value === 'string' && value.length > 0 ? value : null
}

export function nodeOwner(node: KgNode): string | null {
  return prop(node, 'owner_team') ?? prop(node, 'team')
}

export function nodeLanguage(node: KgNode): string | null {
  return prop(node, 'language')
}

export function nodeThreshold(node: KgNode): string | null {
  return prop(node, 'alert_threshold') ?? prop(node, 'threshold')
}

export function nodeRepo(node: KgNode): string | null {
  return prop(node, 'repo')
}

/**
 * Reconstruct a KgSnapshot from a proposal's proposed_changes mutation list.
 */
export function proposalToSnapshot(proposal: KGProposal): KgSnapshot {
  const nodesMap = new Map<string, KgNode>()
  const edges: KgEdge[] = []

  for (const m of proposal.proposed_changes || []) {
    const action = String(m.action || '')
    if (action === 'add_node') {
      const id = String(m.node || '')
      if (!id) continue
      const meta = (m.metadata as Record<string, unknown>) || {}
      nodesMap.set(id, {
        id,
        kind: String(meta.kind || 'service'),
        properties: { ...meta, id },
      })
    } else if (action === 'add_dependency') {
      const from = String(m.from || '')
      const to = String(m.to || '')
      if (from && to) {
        if (!nodesMap.has(from)) {
          nodesMap.set(from, { id: from, kind: 'service', properties: { id: from } })
        }
        if (!nodesMap.has(to)) {
          nodesMap.set(to, { id: to, kind: 'service', properties: { id: to } })
        }
        edges.push({
          from,
          to,
          type: String(m.type || 'DEPENDS_ON'),
          evidence: String(m.evidence || 'proposed'),
        })
      }
    } else if (action === 'add_contains') {
      const from = String(m.from || '')
      const to = String(m.to || '')
      if (from && to) {
        if (!nodesMap.has(from)) {
          nodesMap.set(from, { id: from, kind: 'system', properties: { id: from } })
        }
        if (!nodesMap.has(to)) {
          nodesMap.set(to, { id: to, kind: 'service', properties: { id: to } })
        }
        edges.push({
          from,
          to,
          type: 'CONTAINS',
          evidence: String(m.evidence || 'contains'),
        })
      }
    } else if (action === 'update_metadata') {
      const id = String(m.node || '')
      const field = String(m.field || '')
      if (id && field && nodesMap.has(id)) {
        const existing = nodesMap.get(id)!
        existing.properties[field] = m.value
      }
    }
  }

  return {
    nodes: Array.from(nodesMap.values()),
    edges,
  }
}

/* ── Bootstrap request payloads ─────────────────────────────────────── */

export type BootstrapSource = 'services_json' | 'github_org' | 'github_repo'

export interface RunBootstrapRequest {
  source?: BootstrapSource
  org?: string
  repo?: string
  architecture_type?: string
}

/* ── API calls ──────────────────────────────────────────────────────── */

export async function fetchKgBootstrapStatus(): Promise<KgBootstrapStatus> {
  return api.get<KgBootstrapStatus>('/kg-bootstrap/status')
}

export async function fetchActiveGraph(): Promise<KgSnapshot> {
  return api.get<KgSnapshot>('/kg-bootstrap/active')
}

export async function fetchStagingGraph(): Promise<KgSnapshot> {
  return api.get<KgSnapshot>('/kg-bootstrap/staging')
}

export async function fetchProposals(status?: string): Promise<KGProposal[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : ''
  return api.get<KGProposal[]>(`/kg-proposals${query}`)
}

export async function startBootstrap(
  payload: RunBootstrapRequest = {},
): Promise<{ status: string }> {
  return api.post('/kg-bootstrap/run', payload)
}

export async function approveProposal(
  proposalId: string,
): Promise<KGProposal> {
  return api.post<KGProposal>(`/kg-proposals/${proposalId}/approve`, {})
}

export async function rejectProposal(
  proposalId: string,
  reason?: string,
): Promise<KGProposal> {
  const query = reason ? `?reason=${encodeURIComponent(reason)}` : ''
  return api.post<KGProposal>(`/kg-proposals/${proposalId}/reject${query}`, {})
}

export async function submitProposalFeedback(
  proposalId: string,
  feedback: string,
): Promise<KGProposal> {
  return api.post<KGProposal>(`/kg-proposals/${proposalId}/feedback`, {
    feedback,
  })
}