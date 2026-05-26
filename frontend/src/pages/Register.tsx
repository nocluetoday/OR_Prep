import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'

export function RegisterPage() {
  const { register } = useAuth()
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      await register({
        email,
        password,
        first_name: firstName,
        last_name: lastName,
      })
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <main style={{ maxWidth: 360, margin: '4rem auto', padding: 24 }}>
      <h1>Register</h1>
      <p style={{ color: '#666', fontSize: 14 }}>
        New accounts are created as residents. Faculty and admin elevation happens via the Django admin.
      </p>
      <form onSubmit={onSubmit} style={{ display: 'grid', gap: 12 }}>
        <label>
          Email
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            autoFocus
            style={{ width: '100%', padding: 8, marginTop: 4 }}
          />
        </label>
        <label>
          Password
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            minLength={8}
            style={{ width: '100%', padding: 8, marginTop: 4 }}
          />
        </label>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          <label>
            First name
            <input
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              autoComplete="given-name"
              style={{ width: '100%', padding: 8, marginTop: 4 }}
            />
          </label>
          <label>
            Last name
            <input
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              autoComplete="family-name"
              style={{ width: '100%', padding: 8, marginTop: 4 }}
            />
          </label>
        </div>
        {error && <p style={{ color: 'crimson' }}>{error}</p>}
        <button type="submit" disabled={busy}>
          {busy ? 'Registering…' : 'Create account'}
        </button>
      </form>
      <p style={{ marginTop: 16 }}>
        Already have an account? <Link to="/login">Log in</Link>.
      </p>
    </main>
  )
}
