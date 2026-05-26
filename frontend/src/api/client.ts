// Thin fetch wrapper.
// - Attaches the Authorization header from localStorage when `auth` is not explicitly false.
// - On 401, tries to refresh once via /api/auth/refresh/. If that succeeds, the
//   original request is retried; otherwise tokens are cleared and the 401 propagates.
// - A single in-flight refresh promise is shared so concurrent failures don't
//   trigger multiple refresh calls.

const ACCESS_KEY = 'rlw_access_token'
const REFRESH_KEY = 'rlw_refresh_token'

export const tokens = {
  getAccess(): string | null {
    return localStorage.getItem(ACCESS_KEY)
  },
  getRefresh(): string | null {
    return localStorage.getItem(REFRESH_KEY)
  },
  set(access: string, refresh: string): void {
    localStorage.setItem(ACCESS_KEY, access)
    localStorage.setItem(REFRESH_KEY, refresh)
  },
  clear(): void {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

type FetchOptions = RequestInit & { auth?: boolean }

let refreshInFlight: Promise<boolean> | null = null

function refreshAccess(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight
  refreshInFlight = (async () => {
    const refresh = tokens.getRefresh()
    if (!refresh) return false
    const r = await fetch('/api/auth/refresh/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh }),
    })
    if (!r.ok) {
      tokens.clear()
      return false
    }
    const data = (await r.json()) as { access: string; refresh: string }
    tokens.set(data.access, data.refresh)
    return true
  })().finally(() => {
    refreshInFlight = null
  })
  return refreshInFlight
}

export async function apiFetch(path: string, opts: FetchOptions = {}): Promise<Response> {
  const { auth = true, headers, ...rest } = opts
  const make = (): Promise<Response> => {
    const h = new Headers(headers)
    if (!h.has('Content-Type') && rest.body !== undefined) {
      h.set('Content-Type', 'application/json')
    }
    if (auth) {
      const access = tokens.getAccess()
      if (access) h.set('Authorization', `Bearer ${access}`)
    }
    return fetch(path, { ...rest, headers: h })
  }
  const r = await make()
  if (r.status !== 401 || !auth) return r
  const refreshed = await refreshAccess()
  if (!refreshed) return r
  return make()
}

export async function errorFromResponse(r: Response): Promise<Error> {
  try {
    const body = (await r.json()) as Record<string, unknown>
    const parts = Object.entries(body).map(([k, v]) => {
      const value = Array.isArray(v) ? v.join(', ') : String(v)
      return k === 'detail' || k === 'non_field_errors' ? value : `${k}: ${value}`
    })
    return new Error(parts.join('; ') || `HTTP ${r.status}`)
  } catch {
    return new Error(`HTTP ${r.status}`)
  }
}
