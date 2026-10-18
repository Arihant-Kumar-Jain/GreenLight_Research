import { ChevronDown, LogOut } from 'lucide-react'
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { api, type AuthInfo, type User } from './api'
import { cx } from './ui'

/* Sign in with Google (Google Identity Services). The button returns an ID token; the backend
   verifies it and sets an HttpOnly session cookie. Local dev mode (no GOOGLE_CLIENT_ID) is always signed in. */

type Gis = {
  accounts: {
    id: {
      initialize: (o: { client_id: string; ux_mode: string; callback: (r: { credential: string }) => void }) => void
      renderButton: (el: HTMLElement, o: Record<string, string>) => void
      disableAutoSelect: () => void
    }
  }
}
declare global {
  interface Window { google?: Gis }
}

interface AuthCtx {
  info: AuthInfo | null
  user: User | null
  needsSignIn: boolean
  gisReady: boolean
  error: string | null
  signOut: () => Promise<void>
}

const Ctx = createContext<AuthCtx>({ info: null, user: null, needsSignIn: false, gisReady: false, error: null, signOut: async () => {} })

export const useAuth = () => useContext(Ctx)

let gisScript: Promise<void> | null = null
function loadGis(): Promise<void> {
  gisScript ??= new Promise((resolve, reject) => {
    const s = document.createElement('script')
    s.src = 'https://accounts.google.com/gsi/client'
    s.async = true
    s.onload = () => resolve()
    s.onerror = () => {
      gisScript = null
      reject(new Error('Could not load Google sign-in'))
    }
    document.head.appendChild(s)
  })
  return gisScript
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [info, setInfo] = useState<AuthInfo | null>(null)
  const [gisReady, setGisReady] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(() => api.me().then(setInfo).catch(() => {}), [])
  useEffect(() => { refresh() }, [refresh])

  const clientId = info?.mode === 'google' ? info.google_client_id : null
  useEffect(() => {
    if (!clientId) return
    let live = true
    loadGis()
      .then(() => {
        if (!live || !window.google) return
        window.google.accounts.id.initialize({
          client_id: clientId,
          ux_mode: 'popup',
          callback: async (resp) => {
            try {
              setError(null)
              setInfo(await api.googleLogin(resp.credential))
            } catch (e) {
              setError((e as Error).message)
            }
          },
        })
        setGisReady(true)
      })
      .catch((e: Error) => setError(e.message))
    return () => { live = false }
  }, [clientId])

  const signOut = useCallback(async () => {
    await api.logout().catch(() => {})
    window.google?.accounts.id.disableAutoSelect()
    await refresh()
    window.location.hash = '/'
  }, [refresh])

  const user = info?.user ?? null
  return <Ctx.Provider value={{ info, user, needsSignIn: !!info && !user, gisReady, error, signOut }}>{children}</Ctx.Provider>
}

/** Google's own rendered button (required by Google's branding rules). */
export function GoogleButton({ className }: { className?: string }) {
  const { gisReady, info, error } = useAuth()
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!gisReady || !ref.current || !window.google) return
    window.google.accounts.id.renderButton(ref.current, { theme: 'outline', size: 'large', shape: 'pill', text: 'signin_with', locale: 'en' })
  }, [gisReady])
  if (info?.mode === 'off') return <span className="text-xs text-muted">Sign-in not configured</span>
  return (
    <div className={className}>
      {/* color-scheme: light stops the dark page theme from painting a white box behind Google's iframe */}
      <div ref={ref} className="min-h-[32px]" style={{ colorScheme: 'light' }} />
      {error && <p className="mt-1 text-xs text-stop">{error}</p>}
    </div>
  )
}

function Avatar({ user, size = 28 }: { user: User; size?: number }) {
  const [broken, setBroken] = useState(false)
  if (user.picture && !broken) {
    return <img src={user.picture} alt="" width={size} height={size} referrerPolicy="no-referrer" onError={() => setBroken(true)} className="rounded-full" style={{ width: size, height: size }} />
  }
  return (
    <span className="grid place-items-center rounded-full bg-go-soft text-xs font-semibold text-go" style={{ width: size, height: size }}>
      {(user.name || user.email).trim().charAt(0).toUpperCase()}
    </span>
  )
}

/** Nav slot: Google button when signed out, avatar + menu when signed in, a badge in local dev mode. */
export function UserMenu() {
  const { info, user, signOut } = useAuth()
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  if (!info) return null
  if (info.mode === 'dev') {
    return (
      <span title="No GOOGLE_CLIENT_ID set: running as the built-in local user" className="hidden rounded-full border border-line px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-muted sm:inline">
        Local dev
      </span>
    )
  }
  if (!user) return <GoogleButton />
  return (
    <div ref={box} className="relative">
      <button onClick={() => setOpen((o) => !o)} title={user.email}
        className={cx('flex items-center gap-2 rounded-full border py-0.5 pl-0.5 pr-3 transition', open ? 'border-go/40 bg-sunken' : 'border-line hover:bg-sunken')}>
        <Avatar user={user} />
        <span className="hidden max-w-[9rem] truncate text-[13px] font-medium sm:inline">{(user.name || user.email).split(/[\s@]/)[0]}</span>
        <ChevronDown size={13} className={cx('text-muted transition', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="absolute right-0 top-full z-50 mt-2 w-72 overflow-hidden rounded-2xl border border-line bg-surface shadow-2xl">
          <div className="flex items-center gap-3 p-4">
            <Avatar user={user} size={44} />
            <div className="min-w-0">
              <div className="truncate text-sm font-medium">{user.name ?? user.email}</div>
              <div className="truncate text-xs text-muted">{user.email}</div>
            </div>
          </div>
          <div className="border-t border-line p-2">
            <button onClick={async () => { setOpen(false); await signOut() }}
              className="flex w-full items-center justify-center gap-2 rounded-xl border border-line px-3 py-2 text-[13px] transition hover:border-stop/40 hover:bg-stop-soft hover:text-stop">
              <LogOut size={14} /> Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
