/**
 * In-app notification domain types and API calls.
 *
 * Mirrors backend/app/schemas/notification.py (NotificationListResponse).
 * Surfaces the current user's alert stream — KG build and review results
 * arrive through this channel.
 */

import { api } from '../lib/api'

export interface NotificationItem {
  id: string
  user_email: string
  category: string
  title: string
  message: string
  payload: Record<string, unknown> | null
  read: boolean
  created_at: string
}

export interface NotificationsSummary {
  notifications: NotificationItem[]
  total: number
  unread: number
}

export async function fetchNotifications(): Promise<NotificationsSummary> {
  return api.get<NotificationsSummary>('/notifications?limit=50')
}