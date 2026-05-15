import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { adminApi } from './api';
import { API_BASE } from './api';
import { useI18n } from './i18n';

// === Format helpers ===
function truncate(str) {
  if (!str) return '-';
  return str.length > 8 ? str.substring(0, 8) + '...' : str;
}

function formatDate(isoStr) {
  if (!isoStr) return '-';
  return new Date(isoStr).toLocaleString();
}

function pct(v) {
  return v != null ? `${Math.round(v * 100)}` : '-';
}

export default function DatabaseView() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('sessions');
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [qrSession, setQrSession] = useState(null);

  const [allSessions, setAllSessions] = useState([]);

  // Filters
  const [sessionFilter, setSessionFilter] = useState('');
  const [guestFilter, setGuestFilter] = useState('');
  const [dropdownOpen, setDropdownOpen] = useState(false);

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
        result = await adminApi.getTracks(guestFilter, sessionFilter);
      } else if (activeTab === 'recommendations') {
        result = await adminApi.getRecommendations(sessionFilter);
      } else if (activeTab === 'playlist_tracks') {
        result = await adminApi.getPlaylistTracks(sessionFilter);
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

  useEffect(() => {
    adminApi.getSessions().then(setAllSessions).catch(() => {});
  }, []);

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

  const navigateToPlaylist = (sessionId) => {
    setSessionFilter(sessionId);
    setActiveTab('playlist_tracks');
  };

  const navigateToSession = (item) => {
    localStorage.setItem('cb_session_id', item.id);
    localStorage.setItem('cb_session_data', JSON.stringify({
      session_id: item.id,
      name: item.name,
      genre_seeds: item.genre_seeds || [],
      status: item.status,
    }));
    navigate(`/party/${item.id}`);
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
              src={`${API_BASE}/host/session/${qrSession.id}/qr`}
              alt="QR Code"
              style={{ width: 220, height: 220, border: '3px solid #000', display: 'block', margin: '0 auto 16px' }}
            />
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
              <div style={{ flex: 1, fontSize: '0.75rem', color: '#555', wordBreak: 'break-all', textAlign: 'left', border: '1px solid #eee', padding: 4 }}>
                {window.location.origin}/join/{qrSession.id}
              </div>
              <button
                onClick={() => {
                  navigator.clipboard.writeText(`${window.location.origin}/join/${qrSession.id}`);
                  alert('Copied!');
                }}
                className="nb-btn nb-btn--small nb-btn--primary"
                style={{ fontSize: '0.7rem', padding: '4px 8px' }}
              >
                Copy
              </button>
            </div>
            <button className="nb-btn nb-btn--ghost" onClick={() => setQrSession(null)} style={{ width: '100%' }}>Close</button>
          </div>
        </div>
      )}
      <div style={{ display: 'flex', gap: 12, marginBottom: 24, flexWrap: 'wrap' }}>
        {['sessions', 'guests', 'tracks', 'recommendations', 'playlist_tracks'].map(tab => (
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

      {/* Global Filter Control Panel */}
      {activeTab !== 'sessions' && (
        <div style={{
          padding: '16px 20px', border: '4px solid #000', backgroundColor: '#E0F7FA',
          marginBottom: '24px', display: 'flex', gap: 16, alignItems: 'center',
          boxShadow: '6px 6px 0 #000', flexWrap: 'wrap'
        }}>
          <span style={{ fontWeight: 900, fontSize: '1.1rem' }}>{t.dbFiltersLabel}</span>

          {/* Custom Neubrutalism Dropdown */}
          <div style={{ position: 'relative', flex: '1 1 300px' }}>
            <div
              className="nb-input"
              style={{
                padding: '8px 12px', cursor: 'pointer', margin: 0,
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                backgroundColor: '#fff', userSelect: 'none'
              }}
              onClick={() => setDropdownOpen(!dropdownOpen)}
            >
              <span style={{ fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {sessionFilter ? (allSessions.find(s => s.id === sessionFilter)?.name || truncate(sessionFilter)) : t.dbAllSessions}
              </span>
              <span style={{ fontSize: '0.8rem' }}>{dropdownOpen ? '▲' : '▼'}</span>
            </div>

            {dropdownOpen && (
              <>
                {/* Backdrop to close dropdown on outside click */}
                <div style={{ position: 'fixed', inset: 0, zIndex: 90 }} onClick={() => setDropdownOpen(false)}></div>
                <div style={{
                  position: 'absolute', top: '100%', left: 0, right: 0, marginTop: '8px',
                  backgroundColor: '#fff', border: '4px solid #000', boxShadow: '6px 6px 0 #000',
                  zIndex: 100, maxHeight: '300px', overflowY: 'auto'
                }}>
                  <div
                    style={{ padding: '12px', borderBottom: '3px solid #000', cursor: 'pointer', fontWeight: 900, backgroundColor: !sessionFilter ? '#d4f8d4' : 'transparent' }}
                    onClick={() => { setSessionFilter(''); setDropdownOpen(false); }}
                    onMouseEnter={e => e.currentTarget.style.backgroundColor = !sessionFilter ? '#d4f8d4' : '#f0f0f0'}
                    onMouseLeave={e => e.currentTarget.style.backgroundColor = !sessionFilter ? '#d4f8d4' : 'transparent'}
                  >
                    {t.dbAllSessions}
                  </div>
                  {allSessions.map(s => (
                    <div
                      key={s.id}
                      style={{
                        padding: '12px', borderBottom: '3px solid #000', cursor: 'pointer', fontWeight: 900,
                        backgroundColor: sessionFilter === s.id ? '#d4f8d4' : 'transparent'
                      }}
                      onClick={() => { setSessionFilter(s.id); setDropdownOpen(false); }}
                      onMouseEnter={e => e.currentTarget.style.backgroundColor = sessionFilter === s.id ? '#d4f8d4' : '#f0f0f0'}
                      onMouseLeave={e => e.currentTarget.style.backgroundColor = sessionFilter === s.id ? '#d4f8d4' : 'transparent'}
                    >
                      {s.name} <span style={{ color: '#666', fontSize: '0.85rem', fontWeight: 700 }}>({truncate(s.id)})</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>

          {activeTab === 'tracks' && guestFilter && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, backgroundColor: '#fff', padding: '6px 12px', border: '3px solid #000' }}>
              <span style={{ fontWeight: 700 }}>Guest ID: {truncate(guestFilter)}</span>
              <button className="nb-btn nb-btn--small nb-btn--danger" style={{ padding: '2px 8px', minWidth: 0, fontSize: '0.8rem' }} onClick={() => setGuestFilter('')}>X</button>
            </div>
          )}

          { (sessionFilter || guestFilter) && (
             <button className="nb-btn nb-btn--ghost" onClick={() => { setSessionFilter(''); setGuestFilter(''); }}>
               {t.dbClearFilterAll}
             </button>
          )}
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
                      <td>{(item.genre_seeds || []).join(', ') || '-'}</td>
                      <td>{formatDate(item.created_at)}</td>
                      <td style={{ fontWeight: 'bold', color: '#00A859' }}>{item.guest_count}</td>
                      <td className="actions-cell">
                        {item.status === 'active' && (
                          <button className="nb-btn nb-btn--small nb-btn--primary" onClick={() => navigateToSession(item)} style={{ marginRight: '8px' }}>OPEN</button>
                        )}
                        <button className="nb-btn nb-btn--small nb-btn--ghost" onClick={() => setQrSession(item)} style={{ marginRight: '8px' }}>QR</button>
                        <button className="nb-btn nb-btn--small nb-btn--ghost" onClick={() => navigateToGuests(item.id)} style={{ marginRight: '8px' }}>{t.btnViewGuests}</button>
                        <button className="nb-btn nb-btn--small nb-btn--ghost" onClick={() => navigateToPlaylist(item.id)} style={{ marginRight: '8px' }}>{t.btnViewPlaylist || 'View Playlist'}</button>
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
                      <td>{item.spotify_user_id || '-'}</td>
                      <td>{formatDate(item.joined_at)}</td>
                      <td className="actions-cell">
                        <button className="nb-btn nb-btn--small nb-btn--ghost" onClick={() => navigateToTracks(item.id)} style={{ marginRight: '8px' }}>{t.btnViewTracks}</button>

                        <button
                          className="nb-btn nb-btn--small nb-btn--primary"
                          style={{ marginRight: '8px' }}
                          onClick={async () => {
                            try {
                              const res = await fetch(`${API_BASE}/guest/${item.id}/profile-csv`);
                              if (!res.ok) throw new Error(await res.text());
                              const rows = await res.json();

                              const headers = Object.keys(rows[0] || {});
                              const escape = (v) => {
                                const s = String(v ?? '');
                                if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
                                return s;
                              };

                              const csv = [
                                headers.join(','),
                                ...rows.map(r => headers.map(h => escape(r[h])).join(',')),
                              ].join('\n');

                              const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
                              const url = URL.createObjectURL(blob);
                              const a = document.createElement('a');
                              a.href = url;
                              a.download = `guest_profile_${item.id}.csv`;
                              document.body.appendChild(a);
                              a.click();
                              a.remove();
                              URL.revokeObjectURL(url);
                            } catch (e) {
                              alert(`CSV download failed: ${e.message || e}`);
                            }
                          }}
                        >
                          Download CSV
                        </button>

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
                      <td>{item.popularity ?? '-'}</td>
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
                      <td>{item.is_cold_start ? t.yesColdStart : '-'}</td>
                      <td>{formatDate(item.generated_at)}</td>
                      <td>{item.guest_count}</td>
                    </tr>
                  ))}
                </tbody>
              </>
            )}

            {/* === PLAYLIST TRACKS === */}
            {activeTab === 'playlist_tracks' && (
              <>
                <thead>
                  <tr>
                    <th>{t.colId}</th>
                    <th>{t.colSessionId}</th>
                    <th>{t.colTrackName}</th>
                    <th>{t.colArtistName}</th>
                    <th>Added At</th>
                  </tr>
                </thead>
                <tbody>
                  {data.map(item => (
                    <tr key={item.id}>
                      <td style={{ fontWeight: 'bold' }}>{item.id}</td>
                      <td title={item.session_id}>{truncate(item.session_id)}</td>
                      <td style={{ fontWeight: 'bold', color: '#1DB954' }}>{item.track_name}</td>
                      <td>{item.artist_name}</td>
                      <td>{formatDate(item.added_at)}</td>
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
