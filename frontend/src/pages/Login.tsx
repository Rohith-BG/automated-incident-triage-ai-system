import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Wordmark } from '../components/Icons'
import { api, ApiError } from '../lib/api'
import { setAccessToken } from '../lib/auth'

interface TokenResponse {
  access_token: string
}

/** Lightweight RFC-5322-ish check — catches obvious typos without rejecting
 *  uncommon but valid addresses. */
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/

interface FieldErrors {
  email?: string
  password?: string
}

function validateFields(
  email: string,
  password: string,
): FieldErrors {
  const errors: FieldErrors = {}

  if (!email.trim()) {
    errors.email = 'Email address is required.'
  } else if (!EMAIL_RE.test(email.trim())) {
    errors.email =
      'Enter a valid email address (e.g. name@company.com).'
  }

  if (!password) {
    errors.password = 'Password is required.'
  } else if (password.length < 4) {
    errors.password = 'Password must be at least 4 characters.'
  }

  return errors
}

export default function Login() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [serverError, setServerError] = useState('')
  const [loading, setLoading] = useState(false)
  const [shake, setShake] = useState(false)
  const formRef = useRef<HTMLFormElement>(null)

  /** Validate a single field on blur so the user gets immediate feedback. */
  function handleBlur(field: 'email' | 'password') {
    const errs = validateFields(email, password)
    setFieldErrors((prev) => {
      const next = { ...prev }
      if (errs[field]) {
        next[field] = errs[field]
      } else {
        delete next[field]
      }
      return next
    })
  }

  /** Clear inline error as the user types — re-validate only on blur/submit. */
  function handleChange(
    field: 'email' | 'password',
    value: string,
  ) {
    if (field === 'email') setEmail(value)
    else setPassword(value)

    if (fieldErrors[field]) {
      setFieldErrors((prev) => {
        const next = { ...prev }
        delete next[field]
        return next
      })
    }
    if (serverError) setServerError('')
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setServerError('')

    const errors = validateFields(email, password)
    setFieldErrors(errors)

    if (Object.keys(errors).length > 0) {
      triggerShake()
      return
    }

    setLoading(true)
    try {
      const data = await api.post<TokenResponse>('/auth/login', {
        email: email.trim(),
        password,
      })
      setAccessToken(data.access_token)
      navigate('/dashboard')
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setServerError(
          'The email or password you entered is incorrect. Please check your credentials and try again.',
        )
      } else if (err instanceof ApiError && err.status === 429) {
        setServerError(
          'Too many login attempts. Please wait a moment and try again.',
        )
      } else {
        setServerError(
          'Unable to reach the server. Check your connection and try again.',
        )
      }
      triggerShake()
    } finally {
      setLoading(false)
    }
  }

  function triggerShake() {
    setShake(true)
    setTimeout(() => setShake(false), 500)
  }


  return (
    <div className="flex min-h-dvh flex-col items-center justify-center px-5">
      <div className="w-full max-w-[22rem]">
        <div className="wordmark-enter mb-8 text-center">
          <Wordmark />
        </div>

        <div
          className={`card-enter rounded-2xl border border-grid-major bg-stock p-8 transition-transform ${
            shake ? 'login-shake' : ''
          }`}
        >
          <h1 className="section-type mb-6 text-center text-[1.5rem]">
            Login
          </h1>

          {/* ── Server-level error banner ── */}
          {serverError && (
            <div
              role="alert"
              className="login-error-enter mb-5 flex items-start gap-2.5 rounded-lg border border-signal/25 bg-signal/8 px-3.5 py-3"
            >
              <span
                className="mt-px shrink-0 text-signal"
                aria-hidden="true"
              >
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 16 16"
                  fill="none"
                >
                  <circle
                    cx="8"
                    cy="8"
                    r="7"
                    stroke="currentColor"
                    strokeWidth="1.5"
                  />
                  <path
                    d="M8 4.5v4"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                  />
                  <circle cx="8" cy="11" r="0.75" fill="currentColor" />
                </svg>
              </span>
              <span className="text-[0.8125rem] leading-snug text-signal">
                {serverError}
              </span>
            </div>
          )}

          <form
            ref={formRef}
            onSubmit={handleSubmit}
            noValidate
            className="space-y-5"
          >
            {/* ── Email field ── */}
            <div>
              <div className="mb-1.5 flex items-baseline justify-between">
                <label
                  htmlFor="employee-email"
                  className="legend text-ink"
                >
                  Employee Email ID
                </label>
                {fieldErrors.email && (
                  <span className="legend text-signal" role="alert">
                    Required
                  </span>
                )}
              </div>
              <input
                id="employee-email"
                type="email"
                inputMode="email"
                autoComplete="email"
                placeholder="name@company.com"
                value={email}
                onChange={(e) => handleChange('email', e.target.value)}
                onBlur={() => handleBlur('email')}
                aria-invalid={Boolean(fieldErrors.email)}
                aria-describedby={
                  fieldErrors.email ? 'email-error' : undefined
                }
                className={`login-input data w-full rounded-lg border bg-stock px-3 py-2.5 text-ink outline-none transition-all placeholder:text-ink-3 ${
                  fieldErrors.email
                    ? 'border-signal/60 focus:border-signal'
                    : 'border-grid-major focus:border-ink'
                }`}
              />
              {fieldErrors.email && (
                <p
                  id="email-error"
                  className="login-error-enter mt-1.5 text-[0.75rem] leading-snug text-signal"
                  role="alert"
                >
                  {fieldErrors.email}
                </p>
              )}
            </div>

            {/* ── Password field ── */}
            <div>
              <div className="mb-1.5 flex items-baseline justify-between">
                <label
                  htmlFor="password"
                  className="legend text-ink"
                >
                  Password
                </label>
                {fieldErrors.password && (
                  <span className="legend text-signal" role="alert">
                    Required
                  </span>
                )}
              </div>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) =>
                    handleChange('password', e.target.value)
                  }
                  onBlur={() => handleBlur('password')}
                  aria-invalid={Boolean(fieldErrors.password)}
                  aria-describedby={
                    fieldErrors.password ? 'password-error' : undefined
                  }
                  className={`login-input data w-full rounded-lg border bg-stock px-3 py-2.5 pr-10 text-ink outline-none transition-all placeholder:text-ink-3 ${
                    fieldErrors.password
                      ? 'border-signal/60 focus:border-signal'
                      : 'border-grid-major focus:border-ink'
                  }`}
                />
                <button
                  type="button"
                  tabIndex={-1}
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-3 transition-colors hover:text-ink"
                  aria-label={
                    showPassword ? 'Hide password' : 'Show password'
                  }
                >
                  {showPassword ? (
                    <svg
                      width="18"
                      height="18"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94" />
                      <path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19" />
                      <path d="M14.12 14.12a3 3 0 11-4.24-4.24" />
                      <line x1="1" y1="1" x2="23" y2="23" />
                    </svg>
                  ) : (
                    <svg
                      width="18"
                      height="18"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                      <circle cx="12" cy="12" r="3" />
                    </svg>
                  )}
                </button>
              </div>
              {fieldErrors.password && (
                <p
                  id="password-error"
                  className="login-error-enter mt-1.5 text-[0.75rem] leading-snug text-signal"
                  role="alert"
                >
                  {fieldErrors.password}
                </p>
              )}
            </div>

            {/* ── Submit ── */}
            <button
              type="submit"
              disabled={loading}
              className="login-btn action-primary w-full justify-center rounded-lg disabled:opacity-60"
            >
              {loading ? (
                <span className="inline-flex items-center gap-2">
                  <svg
                    className="animate-spin"
                    width="16"
                    height="16"
                    viewBox="0 0 16 16"
                    fill="none"
                  >
                    <circle
                      cx="8"
                      cy="8"
                      r="6.5"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeDasharray="32"
                      strokeDashoffset="8"
                      strokeLinecap="round"
                    />
                  </svg>
                  Signing in…
                </span>
              ) : (
                'Login'
              )}
            </button>
          </form>

          {/* ── Forgot password link ── */}
          <div className="mt-5 text-center">
            <a
              href="#"
              className="legend text-ink-2 no-underline transition-colors hover:text-ink"
            >
              Forgot password?
            </a>
          </div>


        </div>
      </div>
    </div>
  )
}
