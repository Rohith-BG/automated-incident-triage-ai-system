import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { SignOutMark, UsersMark } from './Icons'
import { api } from '../lib/api'
import { setAccessToken } from '../lib/auth'
import { useCurrentUser, type CurrentUser } from '../lib/useCurrentUser'

const ROLE_LABEL: Record<string, string> = {
  admin: 'Admin',
  developer: 'Developer',
}

function roleLabel(role: string): string {
  if (ROLE_LABEL[role]) return ROLE_LABEL[role]
  if (role) return role.charAt(0).toUpperCase() + role.slice(1)
  return 'Operator'
}

function initialsOf(user: CurrentUser): string {
  const fromName = user.full_name
    .trim()
    .split(/\s+/)
    .map((word) => word.charAt(0))
    .join('')
  if (fromName) return fromName.slice(0, 2).toUpperCase()
  return user.email.charAt(0).toUpperCase()
}

export default function ProfileMenu({ surface = 'stock' }: { surface?: 'stock' | 'white' }) {
  const currentUser = useCurrentUser()
  const [user, setUser] = useState<CurrentUser | null | undefined>(undefined)
  const [open, setOpen] = useState(false)
  const [signingOut, setSigningOut] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    setUser(currentUser)
  }, [currentUser])

  useEffect(() => {
    setOpen(false)
  }, [location.pathname])

  useEffect(() => {
    if (!open) return
    function onPointerDown(event: PointerEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setOpen(false)
        buttonRef.current?.focus()
      }
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  useEffect(() => {
    if (open) panelRef.current?.focus()
  }, [open])

  function handleClick() {
    if (user === null) {
      navigate('/login')
      return
    }
    setOpen((value) => !value)
  }

  async function handleSignOut() {
    if (signingOut) return
    setSigningOut(true)
    try {
      await api.post<{ message: string }>('/auth/logout', {})
    } catch {
      /* refresh cookie may already be gone; clear the local token regardless */
    } finally {
      setAccessToken(null)
      setUser(null)
      setOpen(false)
      navigate('/login')
    }
  }

  const isAdmin = user?.role === 'admin'

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        onClick={handleClick}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={user ? `${user.full_name}, account menu` : 'Account'}
        className={`flex h-9 w-9 items-center justify-center rounded-full border transition-colors ${
          surface === 'white'
            ? 'border-chassis-3 bg-chassis text-phosphor hover:border-ink'
            : 'border-grid-major bg-chassis text-phosphor hover:border-ink'
        }`}
      >
        <span className="data text-[0.6875rem] font-semibold tracking-[0.02em]">
          {user ? initialsOf(user) : '··'}
        </span>
      </button>

      {open && (
        <div
          ref={panelRef}
          role="menu"
          aria-label="Account menu"
          tabIndex={-1}
          className="profile-menu-enter absolute right-0 top-full z-50 mt-2 w-[17.5rem] overflow-hidden rounded-2xl border border-grid-major bg-stock-2 shadow-[0_14px_36px_-14px_rgba(23,26,23,0.5)] outline-none"
        >
          {user === undefined ? (
            <div className="legend px-4 py-5 text-ink-3">Loading profile\u2026</div>
          ) : null}

          {user ? (
            <>
              <div className="px-4 pb-3 pt-4">
                <div className="flex items-center justify-between">
                  <span className="legend text-ink-3">Signed in</span>
                  <span className="legend border border-grid-major px-1.5 py-0.5 text-ink-2">
                    {roleLabel(user.role)}
                  </span>
                </div>

                <div className="mt-3 flex items-center gap-3">
                  <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-chassis text-phosphor">
                    <span className="data text-[0.8125rem] font-semibold tracking-[0.02em]">
                      {initialsOf(user)}
                    </span>
                  </span>
                  <span className="min-w-0">
                    <span className="section-type block truncate text-[0.9375rem] leading-[1.1]">
                      {user.full_name}
                    </span>
                    <span className="data block truncate pt-1 text-[0.625rem] leading-[1.3] text-ink-3">
                      {user.email}
                    </span>
                  </span>
                </div>
              </div>

              <div className="mx-4 h-px bg-grid-major" />

              {isAdmin && (
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => navigate('/admin/users')}
                  className="flex w-full items-center gap-2.5 px-4 py-3 text-left transition-colors hover:bg-stock-3"
                >
                  <UsersMark className="shrink-0 text-ink-3" />
                  <span className="legend text-ink">Manage Users</span>
                </button>
              )}

              <button
                type="button"
                onClick={handleSignOut}
                disabled={signingOut}
                className="flex w-full items-center gap-2.5 px-4 py-3 text-left transition-colors hover:bg-stock-3 disabled:opacity-60"
              >
                <SignOutMark className="shrink-0 text-ink-3" />
                <span className="legend text-ink">
                  {signingOut ? 'Logging out\u2026' : 'Log out'}
                </span>
              </button>
            </>
          ) : null}
        </div>
      )}
    </div>
  )
}