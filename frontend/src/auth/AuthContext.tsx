import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'

import { apiFetch, errorFromResponse, tokens } from '../api/client'

export type Role = 'resident' | 'faculty' | 'admin'

export type User = {
  id: number
  email: string
  first_name: string
  last_name: string
  role: Role
  is_staff: boolean
}

export type RegisterInput = {
  email: string
  password: string
  first_name?: string
  last_name?: string
}

type AuthContextValue = {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (data: RegisterInput) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchMe = useCallback(async (): Promise<User | null> => {
    const r = await apiFetch('/api/me/')
    if (!r.ok) {
      setUser(null)
      return null
    }
    const me = (await r.json()) as User
    setUser(me)
    return me
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      if (!tokens.getAccess()) {
        setLoading(false)
        return
      }
      try {
        await fetchMe()
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [fetchMe])

  const login = useCallback(
    async (email: string, password: string) => {
      const r = await apiFetch('/api/auth/login/', {
        method: 'POST',
        body: JSON.stringify({ email, password }),
        auth: false,
      })
      if (!r.ok) throw await errorFromResponse(r)
      const data = (await r.json()) as { access: string; refresh: string }
      tokens.set(data.access, data.refresh)
      await fetchMe()
    },
    [fetchMe]
  )

  const register = useCallback(
    async (data: RegisterInput) => {
      const r = await apiFetch('/api/auth/register/', {
        method: 'POST',
        body: JSON.stringify(data),
        auth: false,
      })
      if (!r.ok) throw await errorFromResponse(r)
      await login(data.email, data.password)
    },
    [login]
  )

  const logout = useCallback(async () => {
    const refresh = tokens.getRefresh()
    if (refresh) {
      // Best-effort blacklist; ignore network/server failures.
      try {
        await apiFetch('/api/auth/logout/', {
          method: 'POST',
          body: JSON.stringify({ refresh }),
        })
      } catch {
        /* ignore */
      }
    }
    tokens.clear()
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
