import React, { useState, useEffect, useCallback } from 'react';
import { adminApi } from './api';
import { useI18n } from './i18n';

// === Format helpers ===
function truncate(str) {
  if (!str) return '—';
  return str.length > 8 ? str.substring(0, 8) + '...' : str;
}

function formatDate(isoStr) {
  if (!isoStr) return '—';
  return new Date(isoStr).toLocaleString();
}

function pct(v) {
  return v != null ? `${Math.round(v * 100)}` : '—';
}

export default function DatabaseView() {
  const { t } = useI18n();
  const [activeTab, setActiveTab] = useState('sessions');
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [qrSession, setQrSession] = useState(null);
  
  // Filters
  const [sessionFilter, setSessionFilter] = useState('');
  const [guestFilter, setGuestFilter] = useState('');

  const loadData = useCallback(async () => {
    setLoading(true);
    setError('');
    setData([]);
    try {
      let result = [];
      if (activeTab === 'sessions') {
        result = await adminApi.getSessions();
      } else if (activeTab === 'guests') {
        result = await adminApi.getGuests(sessionFilter);
      } else if (activeTab === 'tracks') {
        result = await adminApi.getTracks(guestFilter);
      } else if (activeTab === 'recommendations') {
        result = await adminApi.getRecommendations(sessionFilter);
      }
      setData(result);
    } catch (err) {
      setError(t.dbLoadFailed(err.message));
    } finally {
      setLoading(false);
    }
  }, [activeTab, sessionFilter, guestFilter]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Actions
  const handleDeleteSession = async (id) => {
    if (window.confirm(t.dbConfirmDeleteSession)) {
      try {
        await adminApi.deleteSession(id);
        loadData();
      } catch (e) {
        alert(t.dbDeleteFailed(e.message));
      }
    }
  };

  const handleDeleteGuest = async (id) => {
    if (window.confirm(t.dbConfirmDeleteGuest)) {
      try {
        await adminApi.deleteGuest(id);
        loadData();
      } catch (e) {
        alert(t.dbDeleteFailed(e.message));
      }
    }
  };

  const handleDeleteTrack = async (id) => {
    if (window.confirm(t.dbConfirmDeleteTrack)) {
      try {
        await adminApi.deleteTrack(id);
        loadData();
      } catch (e) {
        alert(t.dbDeleteFailed(e.message));
      }
    }
  };

  const navigateToGuests = (sessionId) => {
    setSessionFilter(sessionId);
    setActiveTab('guests');
  };

  const navigateToTracks = (guestId) => {
    setGuestFilter(guestId);
    setActiveTab('tracks');
  };

  return (
    <div className="page-container">
      {/* QR Modal */}
      {qrSession && (
        <div
          onClick={() => setQrSession(null)}
          style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{ backgroundColor: '#fff', border: '4px solid #000', padding: 32, boxShadow: '8px 8px 0 #000', textAlign: 'center', maxWidth: 320 }}
          >
            <div style={{ fontWeight: 900, fontSize: '1.2rem', marginBottom: 8 }}>{qrSession.name}</div>
            <div style={{ fontSize: '0.8rem', color: '#888', marginBottom: 16 }}>{qrSession.status}</div>
            <img
              src={`${import.meta.env.VITE_API_URL}/host/session/${qrSession.id}/qr`}
              alt="QR Code"
              style={{ width: 220, height: 220, border: '3px solid #000', display: 'block', margin: '0 auto 16px' }}
            />
            <div style={{ fontSize: '0.75rem', color: '#555', wordBreak: 'break-all', marginBottom: 16 }}>
              {import.meta.env.VITE_API_URL.replace(':8000', ':8888')}/join/{qrSession.id}
            </div>
            <button className="nb-btn nb-btn--ghost" onClick={() => setQrSession(null)} style={{ width: '100%' }}>닫기</button>
          </div>
        </div>
      )}
      <div style={{ display: 'flex', gap: 12, marginBottom: 24, flexWrap: 'wrap' }}>
        {['sessions', 'guests', 'tracks', 'recommendations'].map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`nb-btn ${activeTab === tab ? 'nb-btn--primary' : 'nb-btn--ghost'}`}
            style={{ textTransform: 'capitalize' }}
          >
            {tab}
          </button>
        ))}
        <button className="nb-btn nb-btn--ghost" style={{ marginLeft: 'auto' }} onClick={loadData}>
          {t.dbRefresh}
        </button>
      </div>

      {/* Filter Bar */}
      {activeTab === 'guests' && sessionFilter && (
        <div style={{ padding: '12px', border: '3px solid #000', backgroundColor: '#FFFDE7', marginBottom: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontWeight: 700 }}>{t.dbViewingGuestsFor(truncate(sessionFilter))}</span>
          <button className="nb-btn nb-btn--small nb-btn--ghost" onClick={() => setSessionFilter('')}>{t.dbClearFilter}</button>
        </div>
      )}
      {activeTab === 'tracks' && guestFilter && (
        <div style={{ padding: '12px', border: '3px solid #000', backgroundColor: '#FFFDE7', marginBottom: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontWeight: 700 }}>{t.dbViewingTracksFor(truncate(guestFilter))}</span>
          <button className="nb-btn nb-btn--small nb-btn--ghost" onClick={() => setGuestFilter('')}>{t.dbClearFilter}</button>
        </div>
      )}
      {activeTab === 'recommendations' && sessionFilter && (
        <div style={{ padding: '12px', border: '3px solid #000', backgroundColor: '#FFFDE7', marginBottom: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontWeight: 700 }}>{t.dbViewingRecsFor(truncate(sessionFilter))}</span>
          <button className="nb-btn nb-btn--small nb-btn--ghost" onClick={() => setSessionFilter('')}>{t.dbClearFilter}</button>
        </div>
      )}

      {error && (
        <div style={{ color: '#FF4C4C', fontWeight: 700, marginBottom: '20px' }}>
          {error}
        </div>
      )}

      <div className="nb-card" style={{ padding: 0, overflowX: 'auto' }}>
        {loading ? (
          <div style={{ padding: '40px', textAlign: 'center', fontWeight: 700 }}>{t.dbLoading}</div>
        ) : data.length === 0 ? (
          <div style={{ padding: '40px', textAlign: 'center', fontWeight: 700, color: '#888' }}>{t.dbNoData}</div>
        ) : (
          <table className="song-table">
            {/* === SESSIONS === */}
            {activeTab === 'sessions' && (
              <>
                <thead>
                  <tr>
                    <th>{t.colSessionId}</th>
                    <th>{t.colName}</th>
                    <th>{t.colStatus}</th>
                    <th>{t.colGenres}</th>
                    <th>{t.colCreatedAt}</th>
                    <th>{t.colGuestCount}</th>
                    <th>{t.colActions}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.map(item => (
                    <tr key={item.id}>
                      <td title={item.id} style={{ fontWeight: 'bold' }}>{truncate(item.id)}</td>
                      <td>{item.name}</td>
                      <td>
                        <span className="badge" style={{ backgroundColor: item.status === 'active' ? '#d4f8d4' : '#eee' }}>
                          {item.status}
                        </span>
                      </td>
                      <td>{(item.genre_seeds || []).join(', ') || '—'}</td>
                      <td>{formatDate(item.created_at)}</td>
                      <td style={{ fontWeight: 'bold', color: '#00A859' }}>{item.guest_count}</td>
                      <td className="actions-cell">
                        <button className="nb-btn nb-btn--small nb-btn--ghost" onClick={() => setQrSession(item)} style={{ marginRight: '8px' }}>QR</button>
                        <button className="nb-btn nb-btn--small nb-btn--ghost" onClick={() => navigateToGuests(item.id)} style={{ marginRight: '8px' }}>{t.btnViewGuests}</button>
                        <button className="nb-btn nb-btn--small nb-btn--danger" onClick={() => handleDeleteSession(item.id)}>{t.btnDelete}</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </>
            )}

            {/* === GUESTS === */}
            {activeTab === 'guests' && (
              <>
                <thead>
                  <tr>
                    <th>{t.colGuestId}</th>
                    <th>{t.colSessionId}</th>
                    <th>{t.colDisplayName}</th>
                    <th>{t.colSpotifyUserId}</th>
                    <th>{t.colJoinedAt}</th>
                    <th>{t.colActions}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.map(item => (
                    <tr key={item.id}>
                      <td title={item.id} style={{ fontWeight: 'bold' }}>{truncate(item.id)}</td>
                      <td title={item.session_id}>{truncate(item.session_id)}</td>
                      <td>{item.display_name}</td>
                      <td>{item.spotify_user_id || '—'}</td>
                      <td>{formatDate(item.joined_at)}</td>
                      <td className="actions-cell">
                        <button className="nb-btn nb-btn--small nb-btn--ghost" onClick={() => navigateToTracks(item.id)} style={{ marginRight: '8px' }}>{t.btnViewTracks}</button>
                        <button className="nb-btn nb-btn--small nb-btn--danger" onClick={() => handleDeleteGuest(item.id)}>{t.btnDelete}</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </>
            )}

            {/* === TRACKS === */}
            {activeTab === 'tracks' && (
              <>
                <thead>
                  <tr>
                    <th>{t.colId}</th>
                    <th>{t.colGuestId}</th>
                    <th>{t.colTrackName}</th>
                    <th>{t.colArtistName}</th>
                    <th>{t.colPopularity}</th>
                    <th>{t.colDanceability}</th>
                    <th>{t.colEnergy}</th>
                    <th>{t.colValence}</th>
                    <th>{t.colActions}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.map(item => (
                    <tr key={item.id}>
                      <td>{item.id}</td>
                      <td title={item.guest_id}>{truncate(item.guest_id)}</td>
                      <td style={{ fontWeight: 'bold' }}>{item.track_name}</td>
                      <td>{item.artist_name}</td>
                      <td>{item.popularity ?? '—'}</td>
                      <td>{pct(item.danceability)}</td>
                      <td>{pct(item.energy)}</td>
                      <td>{pct(item.valence)}</td>
                      <td className="actions-cell">
                        <button className="nb-btn nb-btn--small nb-btn--danger" onClick={() => handleDeleteTrack(item.id)}>{t.btnDelete}</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </>
            )}

            {/* === RECOMMENDATIONS === */}
            {activeTab === 'recommendations' && (
              <>
                <thead>
                  <tr>
                    <th>{t.colRank}</th>
                    <th>{t.colSessionId}</th>
                    <th>{t.colTrackName}</th>
                    <th>{t.colArtistName}</th>
                    <th>{t.colScore}</th>
                    <th>{t.colColdStart}</th>
                    <th>{t.colGeneratedAt}</th>
                    <th>{t.colGuestCount}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.map(item => (
                    <tr key={item.id}>
                      <td style={{ fontWeight: 'bold', fontSize: '1.2rem', color: '#00A859' }}>{item.rank}</td>
                      <td title={item.session_id}>{truncate(item.session_id)}</td>
                      <td style={{ fontWeight: 'bold' }}>{item.track_name}</td>
                      <td>{item.artist_name}</td>
                      <td style={{ fontWeight: 'bold' }}>{pct(item.score)}</td>
                      <td>{item.is_cold_start ? t.yesColdStart : '—'}</td>
                      <td>{formatDate(item.generated_at)}</td>
                      <td>{item.guest_count}</td>
                    </tr>
                  ))}
                </tbody>
              </>
            )}
          </table>
        )}
      </div>
    </div>
  );
}
