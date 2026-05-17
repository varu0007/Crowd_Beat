import React, { useEffect, useMemo, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useI18n } from './i18n'
import { api } from './api'

export default function GuestEntry() {
  const { t } = useI18n()
  const { sessionId } = useParams()
  const navigate = useNavigate()

  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [error, setError] = useState('')
  const [guestId, setGuestId] = useState('')
  const [approvalStatus, setApprovalStatus] = useState('idle')
  const [submitting, setSubmitting] = useState(false)

  const isDisabled = useMemo(() => {
    const u = (username || '').trim()
    const e = (email || '').trim()
    return u.length < 2 || !e.includes('@')
  }, [username, email])

  useEffect(() => {
    if (!guestId || approvalStatus !== 'pending') return undefined

    const poll = async () => {
      try {
        const status = await api.getGuestApprovalStatus(guestId)
        setApprovalStatus(status.approval_status || 'pending')
      } catch (err) {
        setError(err.message || 'Failed to check approval status')
      }
    }

    const timer = setInterval(poll, 3000)
    poll()
    return () => clearInterval(timer)
  }, [guestId, approvalStatus])

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')

    const u = (username || '').trim()
    const em = (email || '').trim()
    if (u.length < 2) return setError('Please enter your username')
    if (!em.includes('@')) return setError('Please enter a valid email')
    if (!sessionId) return setError('Missing session id')

    setSubmitting(true)
    try {
      const request = await api.requestGuestApproval(sessionId, { username: u, email: em })
      setGuestId(request.guest_id)
      setApprovalStatus(request.approval_status || 'pending')
    } catch (err) {
      setError(err.message || 'Approval request failed')
    } finally {
      setSubmitting(false)
    }
  }

  const handleConnectSpotify = () => {
    const u = (username || '').trim()
    const em = (email || '').trim()
    const url = api.guestLoginWithProfileUrl(sessionId, { username: u, email: em }, guestId)
    window.location.href = url
  }

  const isPending = approvalStatus === 'pending'
  const isApproved = approvalStatus === 'approved' || approvalStatus === 'connected'

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
            disabled={isPending || isApproved}
            style={{ padding: 12, border: '3px solid #000', fontSize: '1rem' }}
          />
        </label>

        <label style={{ display: 'flex', flexDirection: 'column', gap: 6, fontWeight: 800 }}>
          Email
          <input
            value={email}
            onChange={(ev) => setEmail(ev.target.value)}
            placeholder="e.g. sam@email.com"
            disabled={isPending || isApproved}
            style={{ padding: 12, border: '3px solid #000', fontSize: '1rem' }}
          />
        </label>

        {error ? (
          <div style={{ background: '#FF4C4C', color: '#fff', padding: 10, border: '3px solid #000', fontWeight: 900 }}>
            {error}
          </div>
        ) : null}

        {isPending ? (
          <div style={{ padding: 14, border: '3px solid #000', background: '#FFF4B8', fontWeight: 900 }}>
            We're authorizing you wait please
          </div>
        ) : null}

        {isApproved ? (
          <>
            <div style={{ padding: 14, border: '3px solid #000', background: '#D4F8D4', fontWeight: 900 }}>
              you're authorized, connect to spotify
            </div>
            <button
              type="button"
              className="nb-btn nb-btn--primary"
              onClick={handleConnectSpotify}
              style={{ padding: '12px 16px', fontSize: '1rem', fontWeight: 900 }}
            >
              {t.connectSpotify || 'Connect Spotify'}
            </button>
          </>
        ) : null}

        {!isPending && !isApproved ? (
          <button
            type="submit"
            disabled={isDisabled || submitting}
            className="nb-btn nb-btn--primary"
            style={{ padding: '12px 16px', fontSize: '1rem', fontWeight: 900, cursor: isDisabled || submitting ? 'not-allowed' : 'pointer' }}
          >
            {submitting ? 'Submitting...' : (t.connectSpotify || 'Continue to Spotify')}
          </button>
        ) : null}

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
