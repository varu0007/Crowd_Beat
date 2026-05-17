import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useCrowdBeatWS } from './hooks/useCrowdBeatWS';
import { api } from './api';
import { useI18n } from './i18n';
import { Loader2, Monitor, Headphones, CheckCircle2, XCircle } from 'lucide-react';

export default function PartyLobby() {
  const { t } = useI18n();
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const { guestCount, isConnected } = useCrowdBeatWS(sessionId);

  useEffect(() => {
    api.getSession(sessionId)
      .then(data => { setSession(data); setLoading(false); })
      .catch(() => { navigate('/', { replace: true }); });
  }, [sessionId, navigate]);

  const handleClose = async () => {
    if (!window.confirm(t.confirmCloseSessionLobby)) return;
    try {
      await api.closeSession(sessionId);
      navigate('/');
    } catch (e) {
      alert(t.closeFailed(e.message));
    }
  };

  if (loading) {
    return (
      <div className="page-container" style={{ textAlign: 'center', paddingTop: 100 }}>
        <div style={{ display: 'flex', justifyContent: 'center' }}>
          <Loader2 size={48} className="animate-spin" />
        </div>
        <div style={{ fontWeight: 700, marginTop: 12 }}>{t.dbLoading}</div>
      </div>
    );
  }

  return (
    <div className="page-container" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 'calc(100vh - 80px)' }}>
      {/* æ ‡é¢˜åŒº */}
      <div style={{ textAlign: 'center', marginBottom: 40 }}>
        <h1 style={{ fontSize: '2.5rem', fontWeight: 900, textTransform: 'uppercase', margin: 0 }}>
          {session?.name || 'æ´¾å¯¹'}
        </h1>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, marginTop: 12 }}>
          <span className="badge" style={{ backgroundColor: '#00A859', color: '#fff', border: '3px solid #000', fontSize: '0.85rem', padding: '4px 12px' }}>
            ACTIVE
          </span>
          <span style={{ fontWeight: 700, color: '#555', display: 'flex', alignItems: 'center', gap: 6 }}>
            {isConnected ? <CheckCircle2 size={18} color="#00A859" /> : <XCircle size={18} color="#FF4C4C" />} {t.currentGuestsX(guestCount)}
          </span>
        </div>
      </div>

      {/* ä¸¤ä¸ªå¤§æŒ‰é’® */}
      <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', justifyContent: 'center', maxWidth: 700, width: '100%' }}>
        {/* å±•ç¤ºå±å¡ç‰‡ */}
        <div
          className="nb-card nb-card--interactive"
          onClick={() => window.open(`/display/${sessionId}`, '_blank')}
          style={{ flex: '1 1 280px', maxWidth: 320, cursor: 'pointer', textAlign: 'center', padding: '40px 30px' }}
        >
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 16 }}>
            <Monitor size={48} />
          </div>
          <div style={{ fontSize: '1.4rem', fontWeight: 900, textTransform: 'uppercase', marginBottom: 8 }}>
            {t.displayScreen}
          </div>
          <div style={{ fontSize: '0.95rem', color: '#555', fontWeight: 600 }}>
            {t.displayScreenDesc}
          </div>
        </div>

        {/* DJ å·¥ä½œå°å¡ç‰‡ */}
        <div
          className="nb-card nb-card--interactive"
          onClick={() => navigate(`/dj/${sessionId}`)}
          style={{ flex: '1 1 280px', maxWidth: 320, cursor: 'pointer', textAlign: 'center', padding: '40px 30px' }}
        >
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 16 }}>
            <Headphones size={48} />
          </div>
          <div style={{ fontSize: '1.4rem', fontWeight: 900, textTransform: 'uppercase', marginBottom: 8 }}>
            {t.djWorkstation}
          </div>
          <div style={{ fontSize: '0.95rem', color: '#555', fontWeight: 600 }}>
            {t.djWorkstationDesc}
          </div>
        </div>
      </div>

      {/* åº•éƒ¨ç»“æŸæ´¾å¯¹ */}
      <div style={{ marginTop: 48, textAlign: 'center' }}>
        <button
          onClick={handleClose}
          style={{
            background: 'none', border: 'none', color: '#FF4C4C', fontWeight: 700,
            fontSize: '0.9rem', cursor: 'pointer', textDecoration: 'underline',
            fontFamily: 'inherit',
          }}
        >
          {t.endParty}
        </button>
      </div>
    </div>
  );
}
