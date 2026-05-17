import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useCrowdBeatWS } from './hooks/useCrowdBeatWS';
import { api, API_BASE } from './api';
import { useI18n } from './i18n';
import { Mic, Headphones } from 'lucide-react';

export default function DisplayScreen() {
  const { t } = useI18n();
  const { sessionId } = useParams();
  const [session, setSession] = useState(null);
  const [playlistTracks, setPlaylistTracks] = useState([]);

  const { guestCount, isConnected } = useCrowdBeatWS(sessionId);

  // Fetch session info
  useEffect(() => {
    if (!sessionId) return;
    api.getSession(sessionId).then(d => setSession(d)).catch(() => {});
  }, [sessionId]);

  // Poll playlist tracks every 10 seconds
  useEffect(() => {
    if (!sessionId) return;
    const fetchTracks = () => {
      api.getDjPlaylistTracks(sessionId)
        .then(data => setPlaylistTracks(data.tracks || []))
        .catch(() => {});
    };
    fetchTracks(); // initial
    const interval = setInterval(fetchTracks, 10000);
    return () => clearInterval(interval);
  }, [sessionId]);

  return (
    <div style={{
      minHeight: '100vh', backgroundColor: '#0a0a0a', color: '#fff',
      fontFamily: "'Space Grotesk', 'Inter', sans-serif",
      display: 'flex', padding: '40px 48px', gap: 48,
    }}>
      {/* å·¦åˆ— 40% */}
      <div style={{ width: '40%', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 36 }}>
        {/* Logo */}
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '3.5rem', fontWeight: 900, letterSpacing: '-2px', color: '#FFE600', textTransform: 'uppercase' }}>
            CrowdBeat
          </div>
          <div style={{ fontSize: '1.8rem', fontWeight: 700, color: '#fff', marginTop: 10, opacity: 0.9 }}>
            {session?.name || t.partyOngoing}
          </div>
        </div>

        {/* QR ç  */}
        <div style={{
          border: '4px solid #FFE600', padding: 16, backgroundColor: '#fff',
          borderRadius: 8, boxShadow: '0 0 40px rgba(255,230,0,0.3)',
          position: 'relative'
        }}>
          <img
            src={`${API_BASE}/host/session/${sessionId}/qr`}
            alt="QR Code"
            style={{ width: 280, height: 280, display: 'block' }}
          />
          <button
            onClick={() => {
              navigator.clipboard.writeText(`${window.location.origin}/join/${sessionId}`);
              alert(t.linkCopied);
            }}
            style={{
              position: 'absolute', bottom: -15, left: '50%', transform: 'translateX(-50%)',
              backgroundColor: '#FFE600', color: '#000', border: '3px solid #000',
              padding: '4px 12px', fontWeight: 900, cursor: 'pointer', fontSize: '0.75rem'
            }}
          >
            {t.copyTestLink}
          </button>
        </div>

        <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#FFE600', textAlign: 'center', marginTop: 10 }}>
          {t.scanToJoin}
        </div>

        {/* è§‚ä¼—æ•°é‡ */}
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '3rem', fontWeight: 900, color: '#00A859' }}>
            <Mic size={40} style={{ display: 'inline', verticalAlign: 'text-bottom', marginRight: 8 }} />
            {guestCount}
          </div>
          <div style={{ fontSize: '1.1rem', fontWeight: 600, color: '#aaa' }}>{t.guestsJoined}</div>
        </div>

        {/* è¿žæŽ¥çŠ¶æ€ */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: '0.95rem', fontWeight: 600, color: '#777' }}>
          <div style={{
            width: 14, height: 14, borderRadius: '50%',
            backgroundColor: isConnected ? '#00A859' : '#555',
            boxShadow: isConnected ? '0 0 12px #00A859' : 'none',
            transition: 'all 0.3s',
          }}></div>
          {isConnected ? t.wsConnected : t.wsDisconnected}
        </div>
      </div>

      {/* å³åˆ— 60% */}
      <div style={{ width: '60%', display: 'flex', flexDirection: 'column' }}>
        <div style={{
          fontSize: '2rem', fontWeight: 900, color: '#FFE600', textTransform: 'uppercase',
          marginBottom: 24, borderBottom: '3px solid #FFE600', paddingBottom: 12,
        }}>
          {t.djTonightPlaylist}
        </div>

        <div style={{ flex: 1, overflowY: 'auto' }}>
          {playlistTracks.length === 0 ? (
            <div style={{ textAlign: 'center', paddingTop: 80 }}>
              <div style={{ marginBottom: 16, opacity: 0.5 }}>
                <Headphones size={64} />
              </div>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, color: '#555' }}>
                {t.waitingForDj} <Headphones size={24} style={{ display: 'inline', verticalAlign: 'text-bottom', marginLeft: 8 }} />
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {playlistTracks.map((track, idx) => (
                <div key={track.spotify_track_id || idx} style={{
                  display: 'flex', alignItems: 'center', gap: 16,
                  padding: '14px 20px', backgroundColor: 'rgba(255,255,255,0.05)',
                  borderLeft: '4px solid #FFE600', borderRadius: 4,
                  animation: 'slideUp 0.4s ease-out',
                }}>
                  <div style={{ fontSize: '1.4rem', fontWeight: 900, color: '#FFE600', width: 40, textAlign: 'center' }}>
                    {idx + 1}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 800, fontSize: '1.2rem', marginBottom: 4 }}>{track.track_name}</div>
                    <div style={{ fontSize: '0.95rem', color: '#aaa', fontWeight: 600 }}>{track.artist_name}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* åº•éƒ¨å°å­— */}
        <div style={{ textAlign: 'center', paddingTop: 24, fontSize: '0.85rem', color: '#555', fontWeight: 600 }}>
          {t.poweredBy}
        </div>
      </div>
    </div>
  );
}
