import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { api } from './api';
import { useI18n } from './i18n';

export default function GuestPlaylistSelect() {
  const { t } = useI18n();
  const { guestId } = useParams();
  const [searchParams] = useSearchParams();
  const sessionId = searchParams.get('session_id');

  const [playlists, setPlaylists] = useState([]);
  const [displayName, setDisplayName] = useState('');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);

  // Track expansion & loading state per playlist
  const [expandedPlaylist, setExpandedPlaylist] = useState(null);
  const [playlistTracks, setPlaylistTracks] = useState({}); // { playlistId: [tracks] }
  const [loadingTracks, setLoadingTracks] = useState(null);
  const [playlistErrors, setPlaylistErrors] = useState({}); // { playlistId: errorMsg }

  // Selected tracks: Map<spotify_track_id, {track info}>
  const [selectedTracks, setSelectedTracks] = useState(new Map());

  useEffect(() => {
    api.getGuestPlaylists(guestId)
      .then(async (data) => {
        setPlaylists(data.playlists);
        setDisplayName(data.display_name);
        setLoading(false);

        // 预加载所有歌单的歌曲
        for (const pl of data.playlists) {
          try {
            const trackData = await api.getPlaylistTracks(guestId, pl.id);
            setPlaylistTracks(prev => ({ ...prev, [pl.id]: trackData.tracks }));
            if (trackData.error) {
              setPlaylistErrors(prev => ({ ...prev, [pl.id]: trackData.error }));
            }
          } catch (err) {
            setPlaylistErrors(prev => ({ ...prev, [pl.id]: t.loadTracksFailed(err.message) }));
            setPlaylistTracks(prev => ({ ...prev, [pl.id]: [] }));
          }
        }
      })
      .catch(err => {
        setError(t.loadPlaylistsFailed(err.message));
        setLoading(false);
      });
  }, [guestId]);

  const togglePlaylist = useCallback((playlistId) => {
    setExpandedPlaylist(prev => prev === playlistId ? null : playlistId);
  }, []);

  const toggleTrack = useCallback((track) => {
    setSelectedTracks(prev => {
      const next = new Map(prev);
      if (next.has(track.spotify_track_id)) {
        next.delete(track.spotify_track_id);
      } else {
        next.set(track.spotify_track_id, track);
      }
      return next;
    });
  }, []);

  const toggleAllInPlaylist = useCallback((playlistId) => {
    const tracks = playlistTracks[playlistId] || [];
    if (!tracks.length) return;

    const allSelected = tracks.every(t => selectedTracks.has(t.spotify_track_id));

    setSelectedTracks(prev => {
      const next = new Map(prev);
      if (allSelected) {
        // Deselect all from this playlist
        tracks.forEach(t => next.delete(t.spotify_track_id));
      } else {
        // Select all from this playlist
        tracks.forEach(t => next.set(t.spotify_track_id, t));
      }
      return next;
    });
  }, [playlistTracks, selectedTracks]);

  const handleSubmit = async () => {
    if (selectedTracks.size === 0) return;
    setSubmitting(true);
    setError(null);
    try {
      const tracksArray = Array.from(selectedTracks.values());
      await api.submitTracks(guestId, tracksArray);
      setDone(true);
    } catch (err) {
      setError(t.submitFailed(err.message));
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="page-container" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '3rem', marginBottom: 16, animation: 'pulse 1.5s infinite' }}>🎵</div>
          <div style={{ fontSize: '1.2rem', fontWeight: 700 }}>{t.loadingPlaylists}</div>
        </div>
      </div>
    );
  }

  if (done) {
    return (
      <div className="page-container" style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh' }}>
        <div className="nb-card" style={{ textAlign: 'center', padding: '40px 20px', maxWidth: 400, width: '100%' }}>
          <div style={{ fontSize: '4rem', marginBottom: 20 }}>🎵</div>
          <h2 style={{ fontSize: '2rem', fontWeight: 900, marginBottom: 16 }}>{t.submittedTitle}</h2>
          <p style={{ fontSize: '1.1rem', fontWeight: 600, color: '#555', marginBottom: 12 }}>
            {t.submittedDesc(selectedTracks.size)}
          </p>
          <p style={{ fontSize: '1rem', color: '#888' }}>
            {t.canClosePage}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div style={{ paddingBottom: '80px' }}>
      <div className="page-container" style={{ padding: '20px', minHeight: 'auto' }}>
        <div style={{ marginBottom: '24px' }}>
          <h1 style={{ fontSize: '1.8rem', fontWeight: 900, marginBottom: '8px', lineHeight: 1.2 }}>
            {t.hi}，<span style={{ color: '#00A859' }}>{displayName}</span>！<br/>{t.selectMusicForParty}
          </h1>
          <p style={{ fontSize: '0.9rem', fontWeight: 700, color: '#666' }}>
            {t.selectPlaylistDesc}
          </p>
        </div>

        {error && (
          <div style={{ backgroundColor: '#FF4C4C', color: '#fff', padding: '12px', border: '3px solid #000', fontWeight: 700, marginBottom: '20px', boxShadow: '4px 4px 0 #000' }}>
            {error}
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {playlists.map(pl => {
            const isExpanded = expandedPlaylist === pl.id;
            const tracks = playlistTracks[pl.id] || [];
            const isLoadingThis = loadingTracks === pl.id;
            const playlistError = playlistErrors[pl.id];
            const selectedInPlaylist = tracks.filter(t => selectedTracks.has(t.spotify_track_id)).length;
            const allSelected = tracks.length > 0 && selectedInPlaylist === tracks.length;

            return (
              <div key={pl.id} style={{ border: '3px solid #000', backgroundColor: '#fff', boxShadow: '4px 4px 0 #000' }}>
                {/* Playlist header */}
                <div
                  onClick={() => togglePlaylist(pl.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '14px',
                    padding: '12px',
                    cursor: 'pointer',
                    backgroundColor: isExpanded ? '#f0f0ec' : '#fff',
                    transition: 'background-color 0.15s ease',
                    borderBottom: isExpanded ? '3px solid #000' : 'none',
                  }}
                >
                  {/* Playlist image */}
                  <div style={{ width: '56px', height: '56px', flexShrink: 0, backgroundColor: '#eee', border: '2px solid #000', overflow: 'hidden' }}>
                    {pl.image_url ? (
                      <img src={pl.image_url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                    ) : (
                      <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.5rem' }}>🎵</div>
                    )}
                  </div>

                  {/* Playlist info */}
                  <div style={{ flex: 1, overflow: 'hidden' }}>
                    <div style={{
                      fontWeight: 900,
                      fontSize: '1.05rem',
                      marginBottom: '2px',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis'
                    }}>
                      {pl.name}
                    </div>
                    <div style={{ fontSize: '0.82rem', color: '#666', fontWeight: 700 }}>
                      {tracks.length > 0 ? tracks.length : pl.track_count} {t.songs}
                      {selectedInPlaylist > 0 && (
                        <span style={{ color: '#00A859', marginLeft: 8 }}>
                          · {t.selectedInPlaylist(selectedInPlaylist)}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Expand arrow */}
                  <div style={{
                    fontSize: '1.2rem',
                    fontWeight: 900,
                    transition: 'transform 0.2s ease',
                    transform: isExpanded ? 'rotate(180deg)' : 'rotate(0)',
                    flexShrink: 0,
                  }}>
                    ▼
                  </div>
                </div>

                {/* Expanded track list */}
                {isExpanded && (
                  <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
                    {isLoadingThis ? (
                      <div style={{ padding: '24px', textAlign: 'center', fontWeight: 700, color: '#888' }}>
                        {t.loadingTracks}
                      </div>
                    ) : playlistError ? (
                      <div style={{ padding: '24px', textAlign: 'center', fontWeight: 700, color: '#e65100', backgroundColor: '#fff3e0' }}>
                        ⚠️ {playlistError}
                      </div>
                    ) : tracks.length === 0 ? (
                      <div style={{ padding: '24px', textAlign: 'center', fontWeight: 700, color: '#888' }}>
                        {t.playlistEmpty}
                      </div>
                    ) : (
                      <>
                        {/* Select all bar */}
                        <div
                          onClick={() => toggleAllInPlaylist(pl.id)}
                          style={{
                            padding: '8px 12px',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '10px',
                            cursor: 'pointer',
                            backgroundColor: '#f8f8f4',
                            borderBottom: '2px solid #eee',
                            fontWeight: 700,
                            fontSize: '0.85rem',
                            color: '#00A859',
                            textTransform: 'uppercase',
                            letterSpacing: '0.5px',
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={allSelected}
                            readOnly
                            style={{ width: 18, height: 18, accentColor: '#00A859', cursor: 'pointer' }}
                          />
                          {allSelected ? t.deselectAll : t.selectAll}
                        </div>

                        {/* Track items */}
                        {tracks.map((track, idx) => {
                          const isTrackSelected = selectedTracks.has(track.spotify_track_id);
                          return (
                            <div
                              key={track.spotify_track_id}
                              onClick={() => toggleTrack(track)}
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '10px',
                                padding: '10px 12px',
                                cursor: 'pointer',
                                backgroundColor: isTrackSelected ? '#e8f5ee' : (idx % 2 === 0 ? '#fff' : '#fafaf7'),
                                borderBottom: '1px solid #eee',
                                transition: 'background-color 0.1s ease',
                              }}
                            >
                              <input
                                type="checkbox"
                                checked={isTrackSelected}
                                readOnly
                                style={{ width: 18, height: 18, accentColor: '#00A859', cursor: 'pointer', flexShrink: 0 }}
                              />
                              <div style={{ flex: 1, overflow: 'hidden' }}>
                                <div style={{
                                  fontWeight: 700,
                                  fontSize: '0.95rem',
                                  whiteSpace: 'nowrap',
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                }}>
                                  {track.track_name}
                                </div>
                                <div style={{
                                  fontSize: '0.8rem',
                                  color: '#888',
                                  fontWeight: 600,
                                  whiteSpace: 'nowrap',
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                }}>
                                  {track.artist_name}
                                </div>
                              </div>
                              {isTrackSelected && (
                                <div style={{
                                  width: '24px', height: '24px',
                                  backgroundColor: '#00A859', border: '2px solid #000',
                                  borderRadius: '50%',
                                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                                  color: '#fff', fontWeight: 900, fontSize: '0.8rem',
                                  flexShrink: 0
                                }}>
                                  ✓
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Bottom action bar */}
      <div style={{
        position: 'fixed',
        bottom: 0, left: 0, right: 0,
        backgroundColor: '#fff',
        borderTop: '4px solid #000',
        padding: '16px 20px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        boxShadow: '0 -4px 0 rgba(0,0,0,0.1)',
        zIndex: 100
      }}>
        <div style={{ fontWeight: 900, fontSize: '1.1rem' }}>
          {t.selectedTracksCount(<span style={{ color: '#00A859', fontSize: '1.3rem' }}>{selectedTracks.size}</span>)}
        </div>

        <button
          onClick={handleSubmit}
          disabled={selectedTracks.size === 0 || submitting}
          className={`nb-btn ${selectedTracks.size > 0 ? 'nb-btn--primary' : ''}`}
          style={{
            opacity: (selectedTracks.size === 0 || submitting) ? 0.6 : 1,
            cursor: (selectedTracks.size === 0 || submitting) ? 'not-allowed' : 'pointer'
          }}
        >
          {submitting ? t.submitting : (selectedTracks.size === 0 ? t.pleaseSelectTracks : t.shareTracks(selectedTracks.size))}
        </button>
      </div>
    </div>
  );
}
