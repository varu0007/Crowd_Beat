import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useCrowdBeatWS } from './hooks/useCrowdBeatWS';
import { api } from './api';
import { useI18n } from './i18n';
import { Mic, CheckCircle2, XCircle, Headphones } from 'lucide-react';

export default function DJWorkstation() {
  const { t } = useI18n();
  const { sessionId } = useParams();
  const navigate = useNavigate();

  const [djConnected, setDjConnected] = useState(false);
  const [addedTracks, setAddedTracks] = useState(new Set());
  const [playlistTracks, setPlaylistTracks] = useState([]);
  const [error, setError] = useState(null);

  const [recHistory, setRecHistory] = useState([]);
  const [historyIdx, setHistoryIdx] = useState(0);

  const { recommendations, guestCount, isConnected } = useCrowdBeatWS(sessionId);

  // Keep track of recommendation history
  useEffect(() => {
    if (recommendations && recommendations.length > 0) {
      setRecHistory(prev => {
        if (prev.length > 0) {
          const lastBatch = prev[prev.length - 1];
          // avoid duplicate consecutive batches
          if (lastBatch.length === recommendations.length && lastBatch[0]?.spotify_track_id === recommendations[0]?.spotify_track_id) {
            return prev;
          }
        }
        const newHistory = [...prev, recommendations];
        setHistoryIdx(newHistory.length - 1);
        return newHistory;
      });
    }
  }, [recommendations]);

  // Load tracks
  useEffect(() => {
    api.getDjPlaylistTracks(sessionId).then(data => {
      if (data.tracks) {
        setPlaylistTracks(data.tracks);
        setAddedTracks(new Set(data.tracks.map(t => t.spotify_track_id)));
      }
    }).catch(() => {});
  }, [sessionId]);


  const handleAddTrack = async (track) => {
    const trackId = track.spotify_track_id;
    if (!trackId) return;
    try {
      await api.addTrackToPlaylist(sessionId, trackId, track.track_name, track.artist_name);
      setAddedTracks(prev => new Set([...prev, trackId]));
      setPlaylistTracks(prev => [...prev, track]);
    } catch (e) { setError(`Add failed: ${e.message}`); }
  };

  const handleRefresh = async () => {
    try { await api.refreshRecommendations(sessionId); }
    catch (e) { alert(`Refresh failed: ${e.message}`); }
  };

  // Track add button
  const AddBtn = ({ track }) => {
    const id = track.spotify_track_id;
    const added = addedTracks.has(id);
    return (
      <button
        className={`nb-btn nb-btn--small ${added ? 'nb-btn--primary' : 'nb-btn--ghost'}`}
        onClick={() => handleAddTrack(track)}
        disabled={added}
        style={{ minWidth: 100, fontSize: '0.8rem' }}
      >
        {added ? t.addedToPlaylist : t.addToPlaylist}
      </button>
    );
  };

  // Track row
  const TrackRow = ({ track, idx, bg = '#fff' }) => (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px',
      border: '3px solid #000', backgroundColor: bg, boxShadow: '4px 4px 0 #000', marginBottom: 10,
    }}>
      <div style={{ fontSize: '1.3rem', fontWeight: 900, color: '#00A859', width: 30, textAlign: 'center' }}>{idx + 1}</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 900, fontSize: '1rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{track.track_name}</div>
        <div style={{ fontSize: '0.85rem', color: '#555', fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{track.artist_name}</div>
      </div>
      <AddBtn track={track} />
    </div>
  );



  return (
    <div className="page-container">
      {error && (
        <div style={{ backgroundColor: '#FF4C4C', color: '#fff', border: '3px solid #000', padding: 12, fontWeight: 700, marginBottom: 20, boxShadow: '4px 4px 0 #000' }}>
          {error}
          <button onClick={() => setError(null)} style={{ float: 'right', background: 'none', border: 'none', color: '#fff', fontWeight: 900, cursor: 'pointer', fontFamily: 'inherit' }}>X</button>
        </div>
      )}

      {/* === Phase 1 and 2: Split columns === */}
      <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap', alignItems: 'flex-start' }}>

        {/* === Phase 1: Select Tracks === */}
        <div className="nb-card" style={{ flex: '1 1 500px', padding: 0, overflow: 'hidden' }}>
        <div style={{ padding: '16px 24px', borderBottom: '4px solid #000', backgroundColor: '#1a1a1a', color: '#FFE600', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 900, textTransform: 'uppercase', margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 28, height: 28, border: '3px solid #FFE600', fontWeight: 900, fontSize: '0.85rem', backgroundColor: 'transparent', color: '#FFE600' }}>1</span>
            {t.recBoard} {recHistory.length > 0 && <span style={{ fontSize: '0.8rem', color: '#aaa', marginLeft: 8 }}>({t.historyVersion}: {historyIdx + 1}/{recHistory.length})</span>}
          </h3>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, fontSize: '0.85rem', fontWeight: 700 }}>
            {recHistory.length > 0 && (
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', borderRight: '2px solid #555', paddingRight: 16 }}>
                <button
                  className="nb-btn nb-btn--small"
                  disabled={historyIdx === 0}
                  onClick={() => setHistoryIdx(i => i - 1)}
                  style={{ padding: '4px 12px', opacity: historyIdx === 0 ? 0.5 : 1 }}
                >
                  {t.prevRecs}
                </button>
                <button
                  className="nb-btn nb-btn--small"
                  disabled={historyIdx === recHistory.length - 1}
                  onClick={() => setHistoryIdx(i => i + 1)}
                  style={{ padding: '4px 12px', opacity: historyIdx === recHistory.length - 1 ? 0.5 : 1 }}
                >
                  {t.latestRecs}
                </button>
              </div>
            )}
            <span><Mic size={16} style={{ display: 'inline', verticalAlign: 'text-bottom' }} /> {guestCount} {t.guestsCountLabel}</span>
            <span>{isConnected ? <CheckCircle2 size={16} color="#00A859" style={{ display: 'inline', verticalAlign: 'text-bottom' }} /> : <XCircle size={16} color="#FF4C4C" style={{ display: 'inline', verticalAlign: 'text-bottom' }} />}</span>
            <button className="nb-btn nb-btn--small nb-btn--ghost" onClick={handleRefresh} style={{ padding: '4px 12px' }}>{t.dbRefresh}</button>
          </div>
        </div>

        <div style={{ overflowX: 'hidden', position: 'relative' }}>
          <div style={{
            display: 'flex',
            transition: 'transform 0.4s cubic-bezier(0.25, 1, 0.5, 1)',
            transform: `translateX(-${historyIdx * 100}%)`
          }}>
            {recHistory.length === 0 ? (
              <div style={{ width: '100%', padding: 24, flex: '0 0 100%', boxSizing: 'border-box' }}>
                <div className="empty-state">
                  <div className="empty-icon"><Headphones size={48} /></div>
                  <div className="empty-title">{t.waitingForGuests}</div>
                  <div className="empty-desc">{t.waitingForGuestsDesc}</div>
                </div>
              </div>
            ) : (
              recHistory.map((batch, idx) => {
                const newHits = batch.filter(r => r.spotify_track_id?.includes('_new_'));
                const guestPicks = batch.filter(r => r.spotify_track_id?.includes('_guest_'));
                return (
                  <div key={idx} style={{ width: '100%', flex: '0 0 100%', padding: 24, boxSizing: 'border-box' }}>
                    <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
                      <div style={{ flex: '1 1 300px', minWidth: 0 }}>
                        <h4 style={{ fontSize: '1.1rem', fontWeight: 900, marginBottom: 14, borderBottom: '3px solid #000', paddingBottom: 8 }}>{t.djNewHits}</h4>
                        {newHits.map((tr, i) => <TrackRow key={tr.spotify_track_id + i} track={tr} idx={i} />)}
                        {newHits.length === 0 && <div style={{ color: '#888', fontWeight: 600 }}>{t.noNewHits}</div>}
                      </div>
                      <div style={{ flex: '1 1 300px', minWidth: 0 }}>
                        <h4 style={{ fontSize: '1.1rem', fontWeight: 900, marginBottom: 14, borderBottom: '3px solid #000', paddingBottom: 8 }}>{t.guestWishes}</h4>
                        {guestPicks.map((tr, i) => <TrackRow key={tr.spotify_track_id + i} track={tr} idx={i} bg="#E8F5E9" />)}
                        {guestPicks.length === 0 && <div style={{ color: '#888', fontWeight: 600 }}>{t.noGuestWishes}</div>}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* === Phase 2: Selected Playlist === */}
          <div className="nb-card" style={{ flex: '1 1 300px', padding: 0, overflow: 'hidden' }}>
            <div style={{ padding: '16px 24px', borderBottom: '4px solid #000', backgroundColor: '#00A859', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
              <h3 style={{ fontSize: '1.1rem', fontWeight: 900, textTransform: 'uppercase', margin: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', width: 28, height: 28, border: '3px solid #fff', fontWeight: 900, fontSize: '0.85rem', backgroundColor: 'transparent', color: '#fff' }}>2</span>
                {t.currentPlaylist} ({playlistTracks.length} {t.songsCount})
              </h3>
            </div>
            <div style={{ padding: 24, maxHeight: '600px', overflowY: 'auto' }}>
              {playlistTracks.length === 0 ? (
                <div style={{ color: '#888', fontWeight: 600, textAlign: 'center', padding: '20px 0' }}>{t.emptyPlaylist}</div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {playlistTracks.map((tr, i) => (
                    <div key={tr.spotify_track_id + i} style={{
                      display: 'flex', alignItems: 'center', gap: 12, padding: '10px 14px',
                      border: '3px solid #000', backgroundColor: '#fff', boxShadow: '4px 4px 0 #000'
                    }}>
                      <div style={{ fontSize: '1.3rem', fontWeight: 900, color: '#00A859', width: 30, textAlign: 'center' }}>{i + 1}</div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontWeight: 900, fontSize: '1rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{tr.track_name}</div>
                        <div style={{ fontSize: '0.85rem', color: '#555', fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{tr.artist_name}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

      </div>

      {/* Bottom Back Button */}
      <div style={{ display: 'flex', justifyContent: 'center', gap: 32, marginTop: 24 }}>
        <button
          onClick={() => navigate(`/party/${sessionId}`)}
          style={{ background: 'none', border: 'none', color: '#555', fontWeight: 700, fontSize: '0.9rem', cursor: 'pointer', fontFamily: 'inherit' }}
        >
          {t.backToLobby}
        </button>

        <button
          onClick={async () => {
            if (!window.confirm(t.confirmCloseSession || 'Are you sure you want to end this party?')) return;
            try {
              await api.closeSession(sessionId);
              navigate('/');
            } catch (e) {
              alert(t.closeFailed ? t.closeFailed(e.message) : `Close failed: ${e.message}`);
            }
          }}
          style={{
            background: 'none', border: 'none', color: '#FF4C4C', fontWeight: 700,
            fontSize: '0.9rem', cursor: 'pointer', textDecoration: 'underline', fontFamily: 'inherit',
          }}
        >
          {t.endParty || 'End Party'}
        </button>
      </div>
    </div>
  );
}
