import { Link } from 'react-router-dom'

import { useAuth } from '../auth/AuthContext'

export function Header() {
  const { user, logout } = useAuth()
  return (
    <header
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '12px 24px',
        borderBottom: '1px solid #e5e4e7',
      }}
    >
      <Link to="/" style={{ textDecoration: 'none', color: 'inherit', fontWeight: 600 }}>
        Resident Learning Wiki
      </Link>
      <nav style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
        {user ? (
          <>
            <span style={{ fontSize: 14 }}>{user.email}</span>
            <span
              style={{
                padding: '2px 8px',
                borderRadius: 4,
                background: '#eef',
                fontSize: 12,
                textTransform: 'uppercase',
                letterSpacing: 0.5,
              }}
            >
              {user.role}
            </span>
            <button type="button" onClick={() => void logout()}>
              Log out
            </button>
          </>
        ) : (
          <>
            <Link to="/login">Log in</Link>
            <Link to="/register">Register</Link>
          </>
        )}
      </nav>
    </header>
  )
}
