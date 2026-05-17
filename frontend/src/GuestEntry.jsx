import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Music, PenLine, ArrowLeft, Loader2, PartyPopper } from 'lucide-react'
import { api } from './api'
import { useI18n } from './i18n'

export default function GuestEntry() {
  const { t } = useI18n()
  const { sessionId } = useParams()
  const navigate = useNavigate()
  const [mode, setMode] = useState(null) // null | 'spotify' | 'manual'
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (mode === 'spotify' && sessionId) {
      window.location.href = api.guestLoginUrl(sessionId)
    }
  }, [mode, sessionId])

  const handleManualSubmit = async (e) => {
    e.preventDefault()
    if (!name.trim()) { setError('Please enter your name.'); return }
    if (!email.trim()) { setError('Please enter your email.'); return }
    setError('')
    setLoading(true)
    try {
      await api.joinManual(sessionId, name.trim(), email.trim())
      navigate('/guest-success')
    } catch (err) {
      setError(err.message || 'Failed to join. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  // Mode selection screen
  if (mode === null) {
    return (
      <div className="page-container" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
        <div className="nb-card" style={{ textAlign: 'center', padding: '40px 24px', maxWidth: 400, width: '100%' }}>
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 8 }}>
            <PartyPopper size={48} color="#00A859" />
          </div>
          <h2 style={{ fontSize: '1.8rem', fontWeight: 900, marginBottom: 8 }}>Join the Party</h2>
          <p style={{ color: '#555', fontWeight: 600, marginBottom: 32 }}>Choose how you want to join</p>

          <button
            onClick={() => setMode('spotify')}
            style={{
              width: '100%', padding: '14px', fontWeight: 800, fontSize: '1rem',
              backgroundColor: '#1DB954', color: '#fff',
              border: '3px solid #000', boxShadow: '4px 4px 0 #000',
              cursor: 'pointer', marginBottom: 16,
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            }}
          >
            <Music size={18} /> Connect with Spotify
          </button>

          <button
            onClick={() => setMode('manual')}
            style={{
              width: '100%', padding: '14px', fontWeight: 800, fontSize: '1rem',
              backgroundColor: '#fff', color: '#000',
              border: '3px solid #000', boxShadow: '4px 4px 0 #000',
              cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            }}
          >
            <PenLine size={18} /> Join with Name + Email
          </button>
        </div>
      </div>
    )
  }

  // Manual form screen
  if (mode === 'manual') {
    return (
      <div className="page-container" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
        <div className="nb-card" style={{ padding: '40px 24px', maxWidth: 400, width: '100%' }}>
          <button
            onClick={() => { setMode(null); setError('') }}
            style={{ background: 'none', border: 'none', fontWeight: 700, cursor: 'pointer', marginBottom: 16, fontSize: '0.9rem', display: 'flex', alignItems: 'center', gap: 4 }}
          >
            <ArrowLeft size={16} /> Back
          </button>
          <h2 style={{ fontSize: '1.6rem', fontWeight: 900, marginBottom: 24 }}>Enter Your Info</h2>

          <form onSubmit={handleManualSubmit}>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', fontWeight: 700, marginBottom: 6 }}>Name</label>
              <input
                className="nb-input"
                style={{ width: '100%', boxSizing: 'border-box' }}
                placeholder="Your name"
                value={name}
                onChange={e => setName(e.target.value)}
                disabled={loading}
              />
            </div>
            <div style={{ marginBottom: 24 }}>
              <label style={{ display: 'block', fontWeight: 700, marginBottom: 6 }}>Email</label>
              <input
                className="nb-input"
                style={{ width: '100%', boxSizing: 'border-box' }}
                type="email"
                placeholder="your@email.com"
                value={email}
                onChange={e => setEmail(e.target.value)}
                disabled={loading}
              />
            </div>

            {error && (
              <div style={{ color: '#c00', fontWeight: 700, marginBottom: 16, fontSize: '0.9rem' }}>
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              style={{
                width: '100%', padding: '14px', fontWeight: 800, fontSize: '1rem',
                backgroundColor: loading ? '#ccc' : '#000', color: '#fff',
                border: '3px solid #000', boxShadow: loading ? 'none' : '4px 4px 0 #555',
                cursor: loading ? 'not-allowed' : 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
              }}
            >
              {loading ? <><Loader2 size={18} className="animate-spin" /> Joining...</> : 'Join Party'}
            </button>
          </form>
        </div>
      </div>
    )
  }

  // Spotify redirect in progress
  return (
    <div className="page-container" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 12 }}>
          <Loader2 size={48} className="animate-spin" />
        </div>
        <div style={{ fontWeight: 700 }}>{t.redirectingToSpotify}</div>
      </div>
    </div>
  )
}
