/**
 * Landing-page graph data, fetched live from the backend — the source of
 * truth. No topology is hardcoded here: nodes come from GET /services, edges
 * from GET /services/{id}/dependencies, blast radius from
 * GET /services/{id}/blast-radius. A provider reported "unread" (an empty
 * dependency set) degrades gracefully instead of failing the page.
 */

import { api } from '../lib/api'
import { fetchServices, type ServiceSummary } from './dashboard'

export interface ServiceDependency {
  id: string
  dependency_type: string
  owner_team?: string | null
  language?: string | null
  alert_threshold?: string | null
}

export interface ServiceDependencies {
  service_id: string
  dependencies: ServiceDependency[]
}

export interface BlastRadius {
  target_id: string
  affected_services: ServiceSummary[]
  direct_dependents: string[]
  impact_count: number
}

export interface LandingGraph {
  services: ServiceSummary[]
  deps: ServiceDependencies[]
}

export async function fetchLandingGraph(): Promise<LandingGraph> {
  const services = await fetchServices()
  const deps = await Promise.all(
    services.map((s) =>
      api
        .get<ServiceDependencies>(`/services/${encodeURIComponent(s.id)}/dependencies`)
        .catch(() => ({ service_id: s.id, dependencies: [] })),
    ),
  )
  return { services, deps }
}

export async function fetchBlastRadius(serviceId: string): Promise<BlastRadius> {
  return api.get<BlastRadius>(`/services/${encodeURIComponent(serviceId)}/blast-radius`)
}