import { useAuth } from '../auth/AuthContext'

export function HomePage() {
  const { user } = useAuth()
  if (!user) return null
  const displayName = user.first_name?.trim() || user.email
  return (
    <main style={{ maxWidth: 720, margin: '2rem auto', padding: '0 24px' }}>
      <h1>Welcome, {displayName}</h1>
      <p>
        You are signed in as <strong>{user.role}</strong>.
      </p>
      <p style={{ color: '#666' }}>
        The briefing input form replaces this page in Phase B. For now, this page confirms
        the auth round-trip works end-to-end.
      </p>
    </main>
  )
}
