import { type ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <main style={{ padding: 24 }}>Loading…</main>
  if (!user) return <Navigate to="/login" state={{ from: location }} replace />
  return <>{children}</>
}
