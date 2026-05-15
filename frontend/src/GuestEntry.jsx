import React, { useMemo, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useI18n } from './i18n'
import { api, API_BASE } from './api'

export default function GuestEntry() {
  const { t } = useI18n()
  const { sessionId } = useParams()
  const navigate = useNavigate()

  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')

  const isDisabled = useMemo(() => {
    const u = (username || '').trim()
    const e = (email || '').trim()
    return u.length < 2 || !e.includes('@')
  }, [username, email])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')

    const u = (username || '').trim()
    const em = (email || '').trim()
    if (u.length < 2) return setError('Please enter your username')
    if (!em.includes('@')) return setError('Please enter a valid email')
    if (!sessionId) return setError('Missing session id')

    // Call backend to build an authorize URL; it will preserve profile in OAuth state.
    const url = api.guestLoginWithProfileUrl(sessionId, { username: u, email: em })
    window.location.href = url
  }

  return (
    <div style={{ padding: '2rem', maxWidth: 520, margin: '0 auto' }}>
      <h2 style={{ fontWeight: 900, fontSize: '1.6rem', marginBottom: 12 }}>Join with Spotify</h2>
      <p style={{ color: '#666', marginBottom: 18 }}>
        Enter your details so we can associate your Spotify account with your guest profile.
      </p>

      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 6, fontWeight: 800 }}>
          Username
          <input
            value={username}
            onChange={(ev) => setUsername(ev.target.value)}
            placeholder="e.g. Sam"
            style={{ padding: 12, border: '3px solid #000', fontSize: '1rem' }}
          />
        </label>

        <label style={{ display: 'flex', flexDirection: 'column', gap: 6, fontWeight: 800 }}>
          Email
          <input
            value={email}
            onChange={(ev) => setEmail(ev.target.value)}
            placeholder="e.g. sam@email.com"
            style={{ padding: 12, border: '3px solid #000', fontSize: '1rem' }}
          />
        </label>

        {error ? (
          <div style={{ background: '#FF4C4C', color: '#fff', padding: 10, border: '3px solid #000', fontWeight: 900 }}>
            {error}
          </div>
        ) : null}

        <button
          type="submit"
          disabled={isDisabled}
          className="nb-btn nb-btn--primary"
          style={{ padding: '12px 16px', fontSize: '1rem', fontWeight: 900, cursor: isDisabled ? 'not-allowed' : 'pointer' }}
        >
          {t.connectSpotify || 'Continue to Spotify'}
        </button>

        <button
          type="button"
          className="nb-btn nb-btn--ghost"
          onClick={() => navigate('/')}
          style={{ padding: '10px 16px', fontSize: '0.95rem', fontWeight: 800 }}
        >
          {t.backToHome || 'Back'}
        </button>
      </form>
    </div>
  )
}

