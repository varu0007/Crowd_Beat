import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from './api';
import { useI18n } from './i18n';

const GENRES = ['electronic', 'house', 'techno', 'trance', 'dubstep', 'hip-hop', 'pop', 'rock', 'hard-rock', 'metal', 'punk', 'grunge', 'indie', 'jazz', 'blues', 'r-n-b', 'soul', 'funk', 'dance', 'disco', 'k-pop', 'afrobeat', 'reggae', 'latin', 'salsa', 'classical', 'acoustic', 'ambient', 'country', 'gospel', 'synth-pop', 'world-music'];

export default function Home() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [selectedGenres, setSelectedGenres] = useState(new Set(['electronic']));
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');

  const toggleGenre = (g) => {
    const next = new Set(selectedGenres);
    if (next.has(g)) { next.delete(g); } else { if (next.size >= 5) return; next.add(g); }
    setSelectedGenres(next);
  };

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!name.trim()) { setError(t.enterSessionName); return; }
    if (selectedGenres.size === 0) { setError(t.selectAtLeastOneGenre); return; }
    setError(''); setCreating(true);
    try {
      const data = await api.createSession(name, Array.from(selectedGenres));
      navigate(`/party/${data.session_id}`);
    } catch (err) {
      setError(t.createFailed(err.message));
    } finally { setCreating(false); }
  };

  return (
    <div className="page-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 'calc(100vh - 80px)' }}>
      <div className="nb-card" style={{ maxWidth: 560, width: '100%' }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{ fontSize: '3rem', fontWeight: 900, color: '#FFE600', textTransform: 'uppercase', letterSpacing: '-1px', textShadow: '3px 3px 0 #000', WebkitTextStroke: '2px #000' }}>
            CrowdBeat
          </div>
          <div style={{ fontSize: '1rem', fontWeight: 700, color: '#555', marginTop: 4 }}>
            {t.homeSubtitle}
          </div>
        </div>

        {error && <div style={{ backgroundColor: '#FF4C4C', color: '#fff', border: '3px solid #000', padding: 12, fontWeight: 700, marginBottom: 20, boxShadow: '4px 4px 0 #000' }}>{error}</div>}

        <form onSubmit={handleCreate}>
          <div className="form-group">
            <label className="form-label">{t.sessionName}</label>
            <input className="nb-input" placeholder={t.partyTonight} value={name} onChange={e => setName(e.target.value)} />
          </div>
          <div className="form-group" style={{ marginTop: 24 }}>
            <label className="form-label">{t.presetGenres}</label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginTop: 10 }}>
              {GENRES.map(g => {
                const active = selectedGenres.has(g);
                return (
                  <button key={g} type="button" onClick={() => toggleGenre(g)} style={{
                    padding: '8px 16px', fontWeight: 700, textTransform: 'uppercase', border: '3px solid #000',
                    backgroundColor: active ? '#00A859' : '#fff', color: active ? '#fff' : '#000',
                    boxShadow: active ? '2px 2px 0 #000' : '4px 4px 0 #000',
                    transform: active ? 'translate(2px, 2px)' : 'none', cursor: 'pointer', transition: 'all 0.1s',
                    fontSize: '0.9rem',
                  }}>{g}</button>
                );
              })}
            </div>
          </div>
          <div style={{ marginTop: 40, textAlign: 'center' }}>
            <button type="submit" className="nb-btn nb-btn--primary" disabled={creating} style={{ fontSize: '1.1rem', padding: '14px 36px' }}>
              {creating ? t.creating : t.startParty}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
