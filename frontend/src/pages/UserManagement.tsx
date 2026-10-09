import { type CSSProperties, useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import BoardMasthead from '../components/BoardMasthead'
import { UsersMark } from '../components/Icons'
import { api } from '../lib/api'
import { withAuthRetry } from '../lib/auth'

/* ── Types ──────────────────────────────────────────────── */

interface UserRecord {
  id: string
  email: string
  full_name: string
  role: string
  is_active: boolean
  created_at: string
}

interface UserListResponse {
  users: UserRecord[]
  total: number
}

interface CurrentUser {
  id: string
  role: string
}

/* ── Helpers ────────────────────────────────────────────── */

const ROLES = ['admin', 'developer'] as const

function roleBadge(role: string) {
  const color =
    role === 'admin'
      ? 'border-signal text-signal'
      : 'border-grid-major text-ink-2'
  return (
    <span className={`legend rounded-md border px-1.5 py-0.5 ${color}`}>
      {role === 'admin' ? 'Admin' : 'Developer'}
    </span>
  )
}

function statusDot(active: boolean) {
  return (
    <span className="flex items-center gap-1.5">
      <span
        className={`inline-block h-2 w-2 rounded-full ${
          active ? 'bg-[#2e9e4f]' : 'bg-tentative'
        }`}
      />
      <span className="legend text-ink-3">{active ? 'Active' : 'Inactive'}</span>
    </span>
  )
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  })
}

function stagger(delayMs: number): CSSProperties {
  return { animationDelay: `${delayMs}ms` }
}

/* ── Create-user modal ──────────────────────────────────── */

function CreateUserModal({
  onCreated,
  onClose,
}: {
  onCreated: () => void
  onClose: () => void
}) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [fullName, setFullName] = useState('')
  const [role, setRole] = useState<string>('developer')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const backdropRef = useRef<HTMLDivElement>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await withAuthRetry(() =>
        api.post('/auth/register', {
          email,
          password,
          full_name: fullName,
          role,
        }),
      )
      onCreated()
    } catch (err: unknown) {
      const msg =
        typeof err === 'object' && err !== null && 'message' in err
          ? (err as { message: string }).message
          : 'Failed to create user.'
      setError(msg)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div
      ref={backdropRef}
      className="modal-backdrop fixed inset-0 z-50 flex items-center justify-center bg-ink/40 backdrop-blur-[2px]"
      onPointerDown={(e) => {
        if (e.target === backdropRef.current) onClose()
      }}
    >
      <div className="modal-enter w-full max-w-[26rem] overflow-hidden rounded-2xl border border-grid-major bg-stock shadow-[0_18px_48px_-16px_rgba(23,26,23,0.55)]">
        <div className="flex items-center justify-between border-b border-grid-major px-5 py-4">
          <h2 className="section-type text-[1.05rem]">Create user</h2>
          <button
            type="button"
            onClick={onClose}
            className="legend flex h-7 w-7 items-center justify-center rounded-md text-ink-3 transition-colors hover:bg-stock-2 hover:text-ink"
            aria-label="Close"
          >
            ✕
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 px-5 py-5">
          <label className="block">
            <span className="legend text-ink-3">Full name</span>
            <input
              id="create-user-name"
              type="text"
              required
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="login-input mt-1.5 block w-full rounded-lg border border-grid-major bg-stock-2 px-3 py-2.5 text-[0.9375rem] text-ink outline-none transition-colors"
            />
          </label>

          <label className="block">
            <span className="legend text-ink-3">Email</span>
            <input
              id="create-user-email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="login-input mt-1.5 block w-full rounded-lg border border-grid-major bg-stock-2 px-3 py-2.5 text-[0.9375rem] text-ink outline-none transition-colors"
            />
          </label>

          <label className="block">
            <span className="legend text-ink-3">Password</span>
            <input
              id="create-user-password"
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="login-input mt-1.5 block w-full rounded-lg border border-grid-major bg-stock-2 px-3 py-2.5 text-[0.9375rem] text-ink outline-none transition-colors"
            />
            <span className="data-tight mt-1 block text-ink-3">Minimum 8 characters</span>
          </label>

          <fieldset>
            <legend className="legend text-ink-3">Role</legend>
            <div className="mt-1.5 flex gap-3">
              {ROLES.map((r) => (
                <label
                  key={r}
                  className={`flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 transition-colors ${
                    role === r
                      ? 'border-ink bg-stock-3 text-ink'
                      : 'border-grid-major text-ink-3 hover:border-ink-3'
                  }`}
                >
                  <input
                    type="radio"
                    name="role"
                    value={r}
                    checked={role === r}
                    onChange={() => setRole(r)}
                    className="sr-only"
                  />
                  <span className="legend">{r === 'admin' ? 'Admin' : 'Developer'}</span>
                </label>
              ))}
            </div>
          </fieldset>

          {error && (
            <p className="data-tight text-signal">{error}</p>
          )}

          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="action-primary-stock rounded-lg"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="action-primary rounded-lg"
            >
              {submitting ? 'Creating\u2026' : 'Create user'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

/* ── Edit-user inline form ──────────────────────────────── */

function EditUserRow({
  user,
  currentUserId,
  onUpdated,
  onCancel,
}: {
  user: UserRecord
  currentUserId: string
  onUpdated: () => void
  onCancel: () => void
}) {
  const [fullName, setFullName] = useState(user.full_name)
  const [role, setRole] = useState(user.role)
  const [isActive, setIsActive] = useState(user.is_active)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const isSelf = user.id === currentUserId

  async function handleSave() {
    setError(null)
    setSaving(true)
    try {
      await withAuthRetry(() =>
        api.patch(`/auth/users/${user.id}`, {
          full_name: fullName !== user.full_name ? fullName : undefined,
          role: role !== user.role ? role : undefined,
          is_active: isActive !== user.is_active ? isActive : undefined,
        }),
      )
      onUpdated()
    } catch (err: unknown) {
      const msg =
        typeof err === 'object' && err !== null && 'message' in err
          ? (err as { message: string }).message
          : 'Update failed.'
      setError(msg)
    } finally {
      setSaving(false)
    }
  }

  return (
    <tr className="border-b border-grid-major bg-stock-3/50">
      <td className="px-4 py-3">
        <input
          type="text"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          className="login-input w-full rounded-md border border-grid-major bg-stock px-2 py-1.5 text-[0.875rem] text-ink outline-none"
        />
      </td>
      <td className="data-tight px-4 py-3 text-ink-2">{user.email}</td>
      <td className="px-4 py-3">
        <select
          value={role}
          onChange={(e) => setRole(e.target.value)}
          className="legend rounded-md border border-grid-major bg-stock px-2 py-1.5 text-ink outline-none"
        >
          <option value="admin">Admin</option>
          <option value="developer">Developer</option>
        </select>
      </td>
      <td className="px-4 py-3">
        <label className="flex cursor-pointer items-center gap-2">
          <input
            type="checkbox"
            checked={isActive}
            disabled={isSelf}
            onChange={(e) => setIsActive(e.target.checked)}
            className="h-4 w-4 accent-[#2e9e4f]"
          />
          <span className="legend text-ink-3">{isActive ? 'Active' : 'Inactive'}</span>
        </label>
      </td>
      <td className="data-tight px-4 py-3 text-ink-3">{formatDate(user.created_at)}</td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="legend rounded-md border border-ink bg-ink px-2.5 py-1 text-stock transition-colors hover:bg-ink-2 disabled:opacity-50"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="legend rounded-md border border-grid-major px-2.5 py-1 text-ink-2 transition-colors hover:border-ink hover:bg-stock-2 hover:text-ink"
          >
            Cancel
          </button>
        </div>
        {error && <p className="data-tight mt-1 text-signal">{error}</p>}
      </td>
    </tr>
  )
}

/* ── Main page ──────────────────────────────────────────── */

export default function UserManagement() {
  const navigate = useNavigate()
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null)
  const [users, setUsers] = useState<UserRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)

  /* Auth guard: redirect non-admins */
  useEffect(() => {
    withAuthRetry(() => api.get<CurrentUser>('/auth/me'))
      .then((me) => {
        if (me.role !== 'admin') {
          navigate('/dashboard', { replace: true })
        } else {
          setCurrentUser(me)
        }
      })
      .catch(() => navigate('/login', { replace: true }))
  }, [navigate])

  const fetchUsers = useCallback(() => {
    setLoading(true)
    setError(null)
    withAuthRetry(() => api.get<UserListResponse>('/auth/users'))
      .then((data) => {
        setUsers(data.users)
      })
      .catch(() => setError('Failed to load users.'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (currentUser) fetchUsers()
  }, [currentUser, fetchUsers])

  if (!currentUser) {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <span className="legend text-ink-3">Verifying access\u2026</span>
      </div>
    )
  }

  return (
    <div className="min-h-dvh">
      <BoardMasthead />

      <main className="mx-auto w-full max-w-[1400px] px-5 py-10 sm:px-8 lg:px-12">
        {/* Header */}
        <div className="dash-enter mb-8" style={stagger(0)}>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="mb-2 flex items-center gap-3">
                <UsersMark className="text-ink-2" />
                <span className="legend text-ink-3">Administration</span>
              </div>
              <h1 className="verdict-type text-[clamp(2rem,4.5vw,3.25rem)]">
                User Management
              </h1>
              <p className="prose-measure mt-3 text-[1.0625rem] leading-[1.6] text-ink-2">
                Create accounts, assign roles, and control access for every
                operator on the platform.
              </p>
            </div>

            <button
              type="button"
              onClick={() => setShowCreate(true)}
              className="action-primary mt-1 rounded-lg"
            >
              + Create user
            </button>
          </div>
        </div>

        {/* Stats bar */}
        <div className="dash-enter mb-8 grid grid-cols-2 gap-3 sm:grid-cols-4" style={stagger(60)}>
          <div className="rounded-xl border border-grid-major bg-stock px-4 py-3 transition-colors hover:bg-stock-2">
            <span className="legend text-ink-3">Total</span>
            <span className="data mt-1 block text-[1.4rem] leading-none text-ink">
              {users.length}
            </span>
          </div>
          <div className="rounded-xl border border-grid-major bg-stock px-4 py-3 transition-colors hover:bg-stock-2">
            <span className="legend text-ink-3">Admins</span>
            <span className="data mt-1 block text-[1.4rem] leading-none text-ink">
              {users.filter((u) => u.role === 'admin').length}
            </span>
          </div>
          <div className="rounded-xl border border-grid-major bg-stock px-4 py-3 transition-colors hover:bg-stock-2">
            <span className="legend text-ink-3">Developers</span>
            <span className="data mt-1 block text-[1.4rem] leading-none text-ink">
              {users.filter((u) => u.role === 'developer').length}
            </span>
          </div>
          <div className="rounded-xl border border-grid-major bg-stock px-4 py-3 transition-colors hover:bg-stock-2">
            <span className="legend text-ink-3">Inactive</span>
            <span className="data mt-1 block text-[1.4rem] leading-none text-ink">
              {users.filter((u) => !u.is_active).length}
            </span>
          </div>
        </div>

        {/* Error state */}
        {error && (
          <div className="mb-6 rounded-xl border border-signal/30 bg-signal/5 px-4 py-3">
            <p className="data-tight text-signal">{error}</p>
            <button
              type="button"
              onClick={fetchUsers}
              className="legend mt-2 text-ink-2 underline transition-colors hover:text-ink"
            >
              Retry
            </button>
          </div>
        )}

        {/* Loading state */}
        {loading && (
          <div className="py-16 text-center">
            <span className="legend text-ink-3">Loading users\u2026</span>
          </div>
        )}

        {/* User table */}
        {!loading && users.length > 0 && (
          <div
            className="dash-enter overflow-hidden rounded-2xl border border-grid-major bg-stock"
            style={stagger(120)}
          >
            <div className="overflow-x-auto">
              <table className="w-full min-w-[700px] border-collapse">
                <thead>
                  <tr className="bg-stock-2/50 text-left">
                    <th className="table-head-legend px-4 py-3 text-ink-3">Name</th>
                    <th className="table-head-legend px-4 py-3 text-ink-3">Email</th>
                    <th className="table-head-legend px-4 py-3 text-ink-3">Role</th>
                    <th className="table-head-legend px-4 py-3 text-ink-3">Status</th>
                    <th className="table-head-legend px-4 py-3 text-ink-3">Created</th>
                    <th className="table-head-legend px-4 py-3 text-ink-3">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) =>
                    editingId === u.id ? (
                      <EditUserRow
                        key={u.id}
                        user={u}
                        currentUserId={currentUser.id}
                        onUpdated={() => {
                          setEditingId(null)
                          fetchUsers()
                        }}
                        onCancel={() => setEditingId(null)}
                      />
                    ) : (
                      <tr
                        key={u.id}
                        className="user-row border-b border-grid-major transition-colors last:border-b-0 hover:bg-stock-2"
                      >
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-3">
                            <span className="section-type flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-stock-3 text-[0.9375rem]">
                              {u.full_name.trim().charAt(0).toUpperCase()}
                            </span>
                            <span className="flex flex-wrap items-baseline gap-x-2">
                              <span className="section-type text-[0.9375rem]">{u.full_name}</span>
                              {u.id === currentUser.id && (
                                <span className="legend text-ink-3">(you)</span>
                              )}
                            </span>
                          </div>
                        </td>
                        <td className="data-tight px-4 py-3 text-ink-2">{u.email}</td>
                        <td className="px-4 py-3">{roleBadge(u.role)}</td>
                        <td className="px-4 py-3">{statusDot(u.is_active)}</td>
                        <td className="data-tight px-4 py-3 text-ink-3">
                          {formatDate(u.created_at)}
                        </td>
                        <td className="px-4 py-3">
                          <button
                            type="button"
                            onClick={() => setEditingId(u.id)}
                            className="legend rounded-md border border-grid-major px-2.5 py-1 text-ink-2 transition-colors hover:border-ink hover:bg-stock-2 hover:text-ink"
                          >
                            Edit
                          </button>
                        </td>
                      </tr>
                    ),
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Empty state */}
        {!loading && users.length === 0 && !error && (
          <div className="dash-enter rounded-2xl border border-dashed border-grid-major py-16 text-center" style={stagger(120)}>
            <UsersMark className="mx-auto mb-3 text-ink-3" />
            <p className="legend text-ink-3">No users yet</p>
            <button
              type="button"
              onClick={() => setShowCreate(true)}
              className="action-primary mt-4 rounded-lg"
            >
              Create the first user
            </button>
          </div>
        )}
      </main>

      {/* Create modal */}
      {showCreate && (
        <CreateUserModal
          onCreated={() => {
            setShowCreate(false)
            fetchUsers()
          }}
          onClose={() => setShowCreate(false)}
        />
      )}
    </div>
  )
}
