/**
 * Service-registry domain types and API calls.
 *
 * Types mirror the backend Pydantic response schema exactly:
 *   - backend/app/schemas/service_registry.py (ServiceRegistryResponse)
 * The registry is the database-backed source of truth for registered
 * services (repo, architecture type, owner team, language, alert
 * threshold). Relationships are NOT read here — they come from the
 * knowledge graph snapshot (data/kg.ts). All data is read live from
 * the API; nothing is invented.
 */

import { api } from '../lib/api'

export interface RegistryService {
  id: string
  service_id: string
  repo: string
  architecture_type: string
  owner_team: string
  language: string | null
  alert_threshold: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export async function fetchServiceRegistry(): Promise<RegistryService[]> {
  return api.get<RegistryService[]>('/service-registry')
}