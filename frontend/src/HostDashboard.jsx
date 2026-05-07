import React, { useCallback, useEffect, useState } from 'react';
import { useCrowdBeatWS } from './hooks/useCrowdBeatWS';
import { api } from './api';
import { useI18n } from './i18n';

const PRESET_GENRES = ['electronic', 'house', 'hip-hop', 'pop', 'rock', 'jazz', 'r-n-b', 'dance', 'k-pop', 'classical', 'country', 'metal', 'indie', 'soul', 'reggae', 'latin'];

export default function HostDashboard() {
  const { t } = useI18n();
  const [sessionId, setSessionId] = useState(() => localStorage.getItem('cb_session_id'));
  const [sessionData, setSessionData] = useState(() => {
    const saved = localStorage.getItem('cb_session_data');
    return saved ? JSON.parse(saved) : null;
  });

  // Form state
  const [name, setName] = useState('');
  const [selectedGenres, setSelectedGenres] = useState(new Set(['electronic']));
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');

  // Active session state
  const { recommendations, guestCount, isColdStart, isConnected } = useCrowdBeatWS(sessionId);

  const clearSession = useCallback(() => {
    setSessionId(null);
    setSessionData(null);
    setName('');
    setSelectedGenres(new Set(['electronic']));
    localStorage.removeItem('cb_session_id');
    localStorage.removeItem('cb_session_data');
  }, []);

  useEffect(() => {
    if (!sessionId) return;

    let cancelled = false;

    const validateSession = async () => {
      try {
        const data = await api.getSession(sessionId);
        if (cancelled) return;
        setSessionData(data);
        localStorage.setItem('cb_session_data', JSON.stringify(data));
      } catch (err) {
        if (cancelled) return;
        if (err.message === 'Session not found') {
          clearSession();
        }
      }
    };

    validateSession();
    window.addEventListener('focus', validateSession);

    return () => {
      cancelled = true;
      window.removeEventListener('focus', validateSession);
    };
  }, [sessionId, clearSession]);

  const toggleGenre = (g) => {
    const next = new Set(selectedGenres);
    if (next.has(g)) {
      next.delete(g);
    } else {
      if (next.size >= 5) return; // max 5 allowed by Spotify API
      next.add(g);
    }
    setSelectedGenres(next);
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!name.trim()) {
      setError(t.enterSessionName);
      return;
    }
    if (selectedGenres.size === 0) {
      setError(t.selectAtLeastOneGenre);
      return;
    }
    setError('');
    setCreating(true);
    try {
      const data = await api.createSession(name, Array.from(selectedGenres));
      setSessionId(data.session_id);
      setSessionData(data);
      localStorage.setItem('cb_session_id', data.session_id);
      localStorage.setItem('cb_session_data', JSON.stringify(data));
    } catch (err) {
      setError(t.createFailed(err.message));
    } finally {
      setCreating(false);
    }
  };

  const handleRefresh = async () => {
    if (!sessionId) return;
    try {
      await api.refreshRecommendations(sessionId);
    } catch (err) {
      alert(t.refreshFailed(err.message));
    }
  };

  const handleClose = async () => {
    if (!sessionId) return;
    if (window.confirm(t.confirmCloseSession)) {
      try {
        await api.closeSession(sessionId);
        clearSession();
      } catch (err) {
        alert(t.closeFailed(err.message));
      }
    }
  };

  // === 状态一：未创建场次 ===
  if (!sessionId) {
    return (
      <div className="page-container">
        <div className="nb-card" style={{ maxWidth: 600, margin: '0 auto' }}>
          <h2 style={{ fontSize: '2rem', fontWeight: 900, textTransform: 'uppercase', marginBottom: 24, borderBottom: '4px solid #000', paddingBottom: 10 }}>{t.createPartySession}</h2>
          {error && <div style={{ backgroundColor: '#FF4C4C', color: '#fff', border: '3px solid #000', padding: 12, fontWeight: 700, marginBottom: 20, boxShadow: '4px 4px 0 #000' }}>{error}</div>}
          <form onSubmit={handleCreate}>
            <div className="form-group">
              <label className="form-label">{t.sessionName}</label>
              <input 
                className="nb-input" 
                placeholder={t.partyTonight} 
                value={name}
                onChange={e => setName(e.target.value)}
              />
            </div>
            <div className="form-group" style={{ marginTop: 24 }}>
              <label className="form-label">{t.presetGenres}</label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginTop: 10 }}>
                {PRESET_GENRES.map(g => {
                  const active = selectedGenres.has(g);
                  return (
                    <button
                      key={g}
                      type="button"
                      onClick={() => toggleGenre(g)}
                      style={{
                        padding: '6px 12px',
                        fontWeight: 700,
                        textTransform: 'uppercase',
                        border: '3px solid #000',
                        backgroundColor: active ? '#00A859' : '#fff',
                        color: active ? '#fff' : '#000',
                        boxShadow: active ? '2px 2px 0 #000' : '4px 4px 0 #000',
                        transform: active ? 'translate(2px, 2px)' : 'none',
                        cursor: 'pointer',
                        transition: 'all 0.1s'
                      }}
                    >
                      {g}
                    </button>
                  );
                })}
              </div>
            </div>
            <div style={{ marginTop: 40, textAlign: 'right' }}>
              <button type="submit" className="nb-btn nb-btn--primary" disabled={creating}>
                {creating ? t.creating : t.startParty}
              </button>
            </div>
          </form>
        </div>
      </div>
    );
  }

  // === 状态二：已创建场次 ===
  return (
    <div className="page-container" style={{ display: 'flex', gap: 40, flexWrap: 'wrap' }}>
      {/* 左列：状态与控制 */}
      <div style={{ flex: '1 1 300px', maxWidth: 400 }}>
        <div className="nb-card" style={{ textAlign: 'center' }}>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 900, marginBottom: 20, textTransform: 'uppercase' }}>{sessionData?.name || t.partyOngoing}</h2>
          
          <div style={{ border: '4px solid #000', padding: 20, backgroundColor: '#fff', marginBottom: 12, display: 'inline-block', boxShadow: '6px 6px 0 #000' }}>
            <img 
              src={`${import.meta.env.VITE_API_URL}/host/session/${sessionId}/qr`} 
              alt="QR Code" 
              style={{ width: '100%', maxWidth: 200, display: 'block', margin: '0 auto' }} 
            />
          </div>
          <div style={{ fontSize: '0.85rem', fontWeight: 700, color: '#555', wordBreak: 'break-all', marginBottom: 30 }}>
            {window.location.origin}/join/{sessionId}
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '3px dashed #000', paddingTop: 20, marginBottom: 20 }}>
            <div style={{ fontWeight: 700, fontSize: '1.2rem' }}>{t.currentGuests}</div>
            <div style={{ fontSize: '2.5rem', fontWeight: 900, color: '#00A859' }}>{guestCount}</div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, fontSize: '0.9rem', fontWeight: 700, color: '#555', marginBottom: 30 }}>
            <div style={{ width: 14, height: 14, borderRadius: '50%', backgroundColor: isConnected ? '#00A859' : '#ccc', border: '3px solid #000', transition: 'background-color 0.3s' }}></div>
            {isConnected ? t.wsConnected : t.wsDisconnected}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <button className="nb-btn nb-btn--ghost" onClick={handleRefresh} style={{ width: '100%', justifyContent: 'center' }}>
              {t.manualRefresh}
            </button>
            <button className="nb-btn nb-btn--danger" onClick={handleClose} style={{ width: '100%', justifyContent: 'center' }}>
              {t.endSessionBtn}
            </button>
          </div>
        </div>
      </div>

      {/* 右列：推荐列表 */}
      <div style={{ flex: '2 1 500px' }}>
        <div className="nb-card" style={{ padding: 0, overflow: 'hidden' }}>
          <div style={{ padding: '24px 30px', borderBottom: '4px solid #000', backgroundColor: '#1a1a1a', color: '#FFE600', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
            <h2 style={{ fontSize: '1.8rem', fontWeight: 900, textTransform: 'uppercase', margin: 0 }}>{t.currentRecommendations}</h2>
            {isColdStart && (
              <span className="badge" style={{ backgroundColor: '#FFE600', color: '#000', border: '3px solid #000', fontSize: '0.8rem', padding: '6px 12px' }}>
                {t.coldStartNotice}
              </span>
            )}
          </div>
          
          <div style={{ padding: 30 }}>
            {recommendations.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">🎧</div>
                <div className="empty-title">{t.waitingForGuests}</div>
                <div className="empty-desc">{t.waitingForGuestsDesc}</div>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {recommendations.slice(0, 20).map((track, index) => (
                  <div 
                    key={track.spotify_track_id} 
                    style={{ 
                      display: 'flex', 
                      alignItems: 'center', 
                      gap: 16, 
                      padding: '12px 16px', 
                      border: '3px solid #000', 
                      backgroundColor: '#fff', 
                      boxShadow: '4px 4px 0 #000',
                      transition: 'all 0.3s ease',
                      animation: 'slideUp 0.3s ease-out'
                    }}
                  >
                    <div style={{ fontSize: '1.5rem', fontWeight: 900, color: '#00A859', width: 36, textAlign: 'center' }}>
                      {index + 1}
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 900, fontSize: '1.1rem', marginBottom: 2 }}>{track.track_name}</div>
                      <div style={{ fontSize: '0.9rem', color: '#555', fontWeight: 700 }}>{track.artist_name}</div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: '0.8rem', fontWeight: 700, textTransform: 'uppercase', color: '#888', marginBottom: 2 }}>{t.matchScore}</div>
                      <div style={{ fontSize: '1.2rem', fontWeight: 900, color: track.score > 0.8 ? '#FF4C4C' : '#000' }}>
                        {Math.round(track.score * 100)}%
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
