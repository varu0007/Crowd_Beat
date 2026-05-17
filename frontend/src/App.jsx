import React, { useState, useEffect } from 'react';
import { Routes, Route, NavLink, useLocation, useNavigate, Navigate } from 'react-router-dom';
import DatabaseView from './DatabaseView.jsx';
import HostDashboard from './HostDashboard.jsx';
import GuestEntry from './GuestEntry.jsx';
import GuestSuccess from './GuestSuccess.jsx';
import GuestPlaylistSelect from './GuestPlaylistSelect.jsx';
import { addSongsBatch, spotifyTrackToSong, mergeAudioFeatures } from './db.js';
import { useI18n } from './i18n.jsx';

// --- PKCE 辅助函数 ---
const generateRandomString = (length) => {
  const possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  const values = crypto.getRandomValues(new Uint8Array(length));
  return values.reduce((acc, x) => acc + possible[x % possible.length], "");
};

const sha256 = async (plain) => {
  const encoder = new TextEncoder();
  const data = encoder.encode(plain);
  return window.crypto.subtle.digest('SHA-256', data);
};

const base64encode = (input) => {
  return btoa(String.fromCharCode(...new Uint8Array(input)))
    .replace(/=/g, '')
    .replace(/\+/g, '-')
    .replace(/\//g, '_');
};

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// --- 核心配置 ---
const CLIENT_ID = '9ae008bbaf3345ebb6f947fbe22b8eb7';
const REDIRECT_URI = 'http://127.0.0.1:8888/callback';
const SCOPES = 'playlist-read-private playlist-read-collaborative user-library-read user-read-private';

// === Spotify Fetcher Page ===
function SpotifyFetcher() {
  const { t } = useI18n();
  const [accessToken, setAccessToken] = useState(null);
  const [playlists, setPlaylists] = useState([]);
  const [activePlaylist, setActivePlaylist] = useState(null);
  const [tracks, setTracks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [progressInfo, setProgressInfo] = useState('');
  const [savingToDB, setSavingToDB] = useState(false);
  const [saveResult, setSaveResult] = useState('');
  const navigate = useNavigate();
  const location = useLocation();

  // 获取有效 Token (过期则使用 refresh_token 刷新)
  const getValidToken = async () => {
    let token = localStorage.getItem('spotify_access_token');
    const expiresAt = localStorage.getItem('spotify_token_expires_at');
    const refreshToken = localStorage.getItem('spotify_refresh_token');

    if (!token) return null;

    if (Date.now() > parseInt(expiresAt)) {
      if (!refreshToken) return null;
      try {
        const response = await fetch('https://accounts.spotify.com/api/token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: new URLSearchParams({
            client_id: CLIENT_ID,
            grant_type: 'refresh_token',
            refresh_token: refreshToken,
          }),
        });
        if (!response.ok) throw new Error('Refresh failed');
        const data = await response.json();
        token = data.access_token;
        const newExpiresAt = Date.now() + (data.expires_in * 1000);
        
        setAccessToken(token);
        localStorage.setItem('spotify_access_token', token);
        localStorage.setItem('spotify_token_expires_at', newExpiresAt);
        if (data.refresh_token) {
           localStorage.setItem('spotify_refresh_token', data.refresh_token);
        }
      } catch (err) {
        console.error('Token refresh error:', err);
        localStorage.removeItem('spotify_access_token');
        localStorage.removeItem('spotify_refresh_token');
        localStorage.removeItem('spotify_token_expires_at');
        setAccessToken(null);
        return null;
      }
    }
    return token;
  };

  // 页面加载逻辑
  useEffect(() => {
    const init = async () => {
      const urlParams = new URLSearchParams(window.location.search);
      const code = urlParams.get('code');

      if (code) {
        // 同步清理地址栏的 code，防止 React 的多次渲染导致用旧 code 发送重复请求
        navigate('/', { replace: true });
        await exchangeToken(code);
      } else {
        const token = await getValidToken();
        if (token) {
          setAccessToken(token);
          fetchMyPlaylists(token);
        }
      }
    };
    init();
  }, []);

  // 1. 初始化 Spotify 登录流程 (PKCE)
  const handleLogin = async () => {
    const codeVerifier = generateRandomString(64);
    window.localStorage.setItem('code_verifier', codeVerifier);
    
    const hashed = await sha256(codeVerifier);
    const codeChallenge = base64encode(hashed);

    const authUrl = new URL("https://accounts.spotify.com/authorize");
    const params = {
      response_type: 'code',
      client_id: CLIENT_ID,
      scope: SCOPES,
      code_challenge_method: 'S256',
      code_challenge: codeChallenge,
      redirect_uri: REDIRECT_URI,
    };

    authUrl.search = new URLSearchParams(params).toString();
    window.location.href = authUrl.toString();
  };

  // 2. 将 Auth Code 兑换为 Access Token
  const exchangeToken = async (code) => {
    const codeVerifier = localStorage.getItem('code_verifier');
    try {
      const response = await fetch('https://accounts.spotify.com/api/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({
          client_id: CLIENT_ID,
          grant_type: 'authorization_code',
          code,
          redirect_uri: REDIRECT_URI,
          code_verifier: codeVerifier,
        }),
      });

      if (!response.ok) {
        const errText = await response.text();
        throw new Error(`Token exchange failed ${response.status}: ${errText}`);
      }

      const data = await JSON.parse(await response.text());
      const expiresAt = Date.now() + (data.expires_in * 1000);
      
      setAccessToken(data.access_token);
      localStorage.setItem('spotify_access_token', data.access_token);
      localStorage.setItem('spotify_refresh_token', data.refresh_token);
      localStorage.setItem('spotify_token_expires_at', expiresAt);

      await fetchMyPlaylists(data.access_token);
    } catch (err) {
      console.error(err);
      setError(`OAuth 认证失败: ${err.message}`);
    }
  };

  // 3. 获取用户自己的歌单 (GET /v1/me/playlists)
  const fetchMyPlaylists = async (token) => {
    if (!token) return;
    setLoading(true);
    setError('');
    
    let allPlaylists = [];
    let nextUrl = 'https://api.spotify.com/v1/me/playlists?limit=50';
    
    try {
      while (nextUrl) {
        const response = await fetch(nextUrl, { headers: { Authorization: `Bearer ${token}` } });
        if (response.status === 429) {
          const retryAfter = response.headers.get('Retry-After');
          const delay = retryAfter ? parseInt(retryAfter) * 1000 : 2000;
          setProgressInfo(`Rate limited. Waiting for ${delay}ms...`);
          await sleep(delay);
          continue;
        }
        let data;
        const text = await response.text();
        try {
          data = JSON.parse(text);
        } catch (e) {
          throw new Error(`Unexpected API Response: ${text.substring(0, 100)}...`);
        }

        if (!response.ok) {
           throw new Error(`Spotify API Error ${response.status}: ${data?.error?.message || text.substring(0, 50)}`);
        }
        
        allPlaylists = [...allPlaylists, ...data.items];
        setPlaylists(allPlaylists);
        nextUrl = data.next;
        if (nextUrl) await sleep(100);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      setProgressInfo('');
    }
  };

  // 4. 读取具体 Playlist 的歌曲数据
  const fetchPlaylistTracks = async (playlist) => {
    setActivePlaylist(playlist);
    const token = await getValidToken();
    if (!token) return setError('Session expired. Please log in again.');
    
    setLoading(true);
    setError('');
    setTracks([]);
    setSaveResult('');
    
    let allTracks = [];
    let nextUrl = `https://api.spotify.com/v1/playlists/${playlist.id}/items?additional_types=track&limit=50`;

    try {
      while (nextUrl) {
        const response = await fetch(nextUrl, {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (response.status === 429) {
          const retryAfter = response.headers.get('Retry-After');
          const delay = retryAfter ? parseInt(retryAfter) * 1000 : 2000;
          setProgressInfo(`Rate limited. Waiting for ${delay}ms...`);
          await sleep(delay);
          continue;
        }

        let data;
        const text = await response.text();
        try {
          data = JSON.parse(text);
        } catch (e) {
          throw new Error(`Unexpected API Response: ${text.substring(0, 100)}...`);
        }

        if (!response.ok) {
          throw new Error(`Spotify API Error ${response.status}: ${data?.error?.message || text.substring(0, 50)}`);
        }

        const validTracks = data.items
          .map(tObj => tObj.track || tObj.item || tObj) // Fallback for different API response structures
          .filter(track => track && track.name);
          
        allTracks = [...allTracks, ...validTracks];
        setTracks(allTracks);
        
        nextUrl = data.next;
        setProgressInfo(`Fetched ${allTracks.length} / ${data.total || '?'} tracks...`);

        if (nextUrl) await sleep(100);
      }
      setProgressInfo('Fetch complete!');
    } catch (err) {
      setError(err.message);
      setProgressInfo('');
    } finally {
      setLoading(false);
    }
  };

  // 5. 读取 Liked Songs (GET /v1/me/tracks)
  const fetchLikedSongs = async () => {
    setActivePlaylist({
      id: 'liked_songs',
      name: 'Liked Songs',
      uri: 'spotify:user:liked_songs',
      owner: { display_name: 'You' }
    });
    const token = await getValidToken();
    if (!token) return setError('Session expired. Please log in again.');
    
    setLoading(true);
    setError('');
    setTracks([]);
    setSaveResult('');
    
    let allTracks = [];
    let nextUrl = `https://api.spotify.com/v1/me/tracks?limit=50`;

    try {
      while (nextUrl) {
        const response = await fetch(nextUrl, {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (response.status === 429) {
          const retryAfter = response.headers.get('Retry-After');
          const delay = retryAfter ? parseInt(retryAfter) * 1000 : 2000;
          setProgressInfo(`Rate limited. Waiting for ${delay}ms...`);
          await sleep(delay);
          continue;
        }

        let data;
        const text = await response.text();
        try {
          data = JSON.parse(text);
        } catch (e) {
          throw new Error(`Unexpected API Response: ${text.substring(0, 100)}...`);
        }

        if (!response.ok) {
          throw new Error(`Spotify API Error ${response.status}: ${data?.error?.message || text.substring(0, 50)}`);
        }

        const validTracks = data.items
          .map(tObj => tObj.track || tObj.item || tObj)
          .filter(track => track && track.name);
          
        allTracks = [...allTracks, ...validTracks];
        setTracks(allTracks);
        
        nextUrl = data.next;
        setProgressInfo(`Fetched ${allTracks.length} / ${data.total || '?'} tracks...`);

        if (nextUrl) await sleep(100);
      }
      setProgressInfo('Fetch complete!');
    } catch (err) {
      setError(err.message);
      setProgressInfo('');
    } finally {
      setLoading(false);
    }
  };

  // 6. 批量获取 Audio Features (每次最多100个ID)
  const fetchAudioFeaturesBatch = async (trackIds, token) => {
    const features = {};
    const batchSize = 100;

    for (let i = 0; i < trackIds.length; i += batchSize) {
      const batch = trackIds.slice(i, i + batchSize).filter(Boolean);
      if (batch.length === 0) continue;

      setProgressInfo(`Fetching audio features: ${i + batch.length} / ${trackIds.length}...`);

      try {
        const response = await fetch(
          `https://api.spotify.com/v1/audio-features?ids=${batch.join(',')}`,
          { headers: { Authorization: `Bearer ${token}` } }
        );

        if (response.status === 403) {
          // Audio Features API 已弃用，新应用没有权限
          console.warn('Audio Features API access denied (deprecated). Skipping.');
          setProgressInfo('Audio Features API 不可用 (已弃用)，跳过音频特征获取...');
          await sleep(500);
          return features;
        }

        if (response.status === 429) {
          const retryAfter = response.headers.get('Retry-After');
          const delay = retryAfter ? parseInt(retryAfter) * 1000 : 2000;
          setProgressInfo(`Rate limited. Waiting ${delay}ms...`);
          await sleep(delay);
          i -= batchSize; // retry this batch
          continue;
        }

        if (response.ok) {
          const data = await response.json();
          if (data.audio_features) {
            data.audio_features.forEach((af) => {
              if (af && af.id) {
                features[af.id] = af;
              }
            });
          }
        }
      } catch (err) {
        console.warn('Audio features fetch error:', err);
      }

      if (i + batchSize < trackIds.length) await sleep(100);
    }

    return features;
  };

  // 7. Save to Database (with audio features enrichment)
  const handleSaveToDB = async () => {
    if (!activePlaylist || tracks.length === 0) return;
    setSavingToDB(true);
    setSaveResult('');

    try {
      const token = await getValidToken();

      // Step 1: 转换基本元数据
      setProgressInfo('Step 1/3: Extracting track metadata...');
      const songs = tracks.map((t) => spotifyTrackToSong(t, activePlaylist.name, t._addedAt || ''));
      await sleep(200);

      // Step 2: 尝试获取 Audio Features
      setProgressInfo('Step 2/3: Fetching audio features...');
      let enrichedSongs = songs;
      if (token) {
        const trackIds = songs.map((s) => s.id).filter((id) => !id.startsWith('local_') && !id.startsWith('manual_'));
        if (trackIds.length > 0) {
          const audioFeatures = await fetchAudioFeaturesBatch(trackIds, token);
          const featuresCount = Object.keys(audioFeatures).length;
          if (featuresCount > 0) {
            enrichedSongs = songs.map((s) => mergeAudioFeatures(s, audioFeatures[s.id]));
            setProgressInfo(`Audio features obtained for ${featuresCount} / ${trackIds.length} tracks`);
            await sleep(300);
          }
        }
      }

      // Step 3: 保存到 IndexedDB
      setProgressInfo('Step 3/3: Saving to database...');
      const count = await addSongsBatch(enrichedSongs);
      setProgressInfo('');
      setSaveResult(`✓ 已成功保存 ${count} 首歌曲到数据库！(含 ${Object.keys(enrichedSongs[0] || {}).length} 个元数据字段)`);
    } catch (err) {
      setSaveResult(`✗ 保存失败: ${err.message}`);
    } finally {
      setSavingToDB(false);
      setProgressInfo('');
    }
  };

  const handleDownloadJSON = () => {
    if (!activePlaylist || tracks.length === 0) return;
    const exportData = {
      playlist: {
        id: activePlaylist.id,
        name: activePlaylist.name,
        uri: activePlaylist.uri,
        owner: activePlaylist.owner?.display_name,
        total_tracks: tracks.length
      },
      tracks: tracks.map(t => ({
        id: t.id || null,
        name: t.name || 'Unknown',
        artists: t.artists ? t.artists.map(a => a.name) : [],
        album: t.album ? t.album.name : (t.show ? t.show.name : null)
      }))
    };
    const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${activePlaylist.name.replace(/[^a-z0-9]/gi, '_').toLowerCase()}_export.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <div className="page-container">
      <div className="nb-card">
        <h1 style={{
          fontSize: '2.5rem',
          fontWeight: '900',
          textTransform: 'uppercase',
          borderBottom: '4px solid #000',
          paddingBottom: '10px',
          marginBottom: '20px',
          marginTop: 0,
        }}>
          {t.fetcherTitle}
        </h1>
        
        {!accessToken ? (
          <div>
            <p style={{ fontSize: '1.2rem', fontWeight: 'bold' }}>
              {t.authRequired}
            </p>
            <button className="nb-btn" onClick={handleLogin} style={{ marginTop: '10px' }}>
              {t.connectSpotify}
            </button>
          </div>
        ) : (
          <div>
            <div style={{ marginBottom: '20px', fontWeight: 'bold', color: '#00A859', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span>{t.authenticated}</span>
              <button 
                className="nb-btn nb-btn--small nb-btn--ghost"
                onClick={() => {
                  localStorage.clear();
                  window.location.reload();
                }}
              >
                {t.logOut}
              </button>
            </div>

            {!loading && !activePlaylist && (
              <div>
                <h2 style={{ fontSize: '1.5rem', fontWeight: 'bold', marginBottom: '15px' }}>{t.yourLibrary}</h2>
                <div style={{ maxHeight: '400px', overflowY: 'auto', paddingRight: '10px' }}>
                  
                  {/* 特殊处理的 Liked Songs (我喜欢的音乐) */}
                  <div 
                    className="nb-card nb-card--interactive"
                    style={{ padding: '15px', marginBottom: '10px', borderColor: '#00A859', backgroundColor: '#e6ffe6', cursor: 'pointer', boxShadow: '4px 4px 0 #000' }}
                    onClick={() => fetchLikedSongs()}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 'bold', fontSize: '1.2rem', color: '#00A859' }}>{t.likedSongs}</div>
                        <div style={{ fontSize: '0.85rem', color: '#555', marginTop: '4px' }}>
                          Creator: <span style={{fontWeight: 'bold'}}>You</span>
                        </div>
                      </div>
                      <div style={{ fontSize: '0.9rem', color: '#00A859', textAlign: 'right', fontWeight: 'bold' }}>
                        Auto-fetch
                      </div>
                    </div>
                  </div>

                  {/* 普通歌单 */}
                  {playlists.map(pl => (
                    <div 
                      key={pl.id} 
                      className="nb-card nb-card--interactive"
                      style={{ padding: '15px', marginBottom: '10px', cursor: 'pointer', boxShadow: '4px 4px 0 #000' }}
                      onClick={() => fetchPlaylistTracks(pl)}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontWeight: 'bold', fontSize: '1.1rem' }}>{pl.name}</div>
                          <div style={{ fontSize: '0.85rem', color: '#888', marginTop: '4px' }}>
                            Creator: <span style={{fontWeight: 'bold', color: pl.owner?.display_name === 'Spotify' ? '#00A859' : '#000'}}>{pl.owner?.display_name || 'Unknown'}</span>
                          </div>
                        </div>
                        <div style={{ fontSize: '0.9rem', color: '#555', textAlign: 'right' }}>
                          {pl.tracks?.total || pl.items?.total || 0} tracks
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
            
            {activePlaylist && (
               <div>
                 <div style={{ display: 'flex', gap: '10px', marginBottom: '20px', flexWrap: 'wrap' }}>
                   <button 
                      className="nb-btn nb-btn--ghost nb-btn--small"
                      onClick={() => {
                        setActivePlaylist(null);
                        setTracks([]);
                        setSaveResult('');
                      }}
                   >
                     {t.back}
                   </button>
                   {tracks.length > 0 && !loading && (
                     <>
                       <button
                          className="nb-btn nb-btn--primary nb-btn--small"
                          onClick={handleSaveToDB}
                          disabled={savingToDB}
                       >
                         {savingToDB ? t.saving : t.saveToDB}
                       </button>
                       <button
                          className="nb-btn nb-btn--small"
                          onClick={handleDownloadJSON}
                       >
                         {t.downloadJSON}
                       </button>
                     </>
                   )}
                 </div>
                 <h2 style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>
                   {t.inspecting}: {activePlaylist.name}
                 </h2>
                 {saveResult && (
                   <div style={{
                     marginTop: '12px',
                     padding: '12px 18px',
                     border: '3px solid #000',
                     backgroundColor: saveResult.startsWith('✓') ? '#d4f8d4' : '#fdd',
                     fontWeight: 'bold',
                     boxShadow: '3px 3px 0 #000',
                   }}>
                     {saveResult}
                     {saveResult.startsWith('✓') && (
                       <button 
                         className="nb-btn nb-btn--small nb-btn--ghost"
                         style={{ marginLeft: '12px' }}
                         onClick={() => navigate('/database')}
                       >
                         前往数据库查看 →
                       </button>
                     )}
                   </div>
                 )}
               </div>
            )}

          </div>
        )}
      </div>

      {error && (
        <div style={{
          backgroundColor: '#FF4C4C',
          color: '#fff',
          border: '4px solid #000',
          padding: '15px',
          fontWeight: 'bold',
          marginBottom: '20px',
          boxShadow: '4px 4px 0 #000',
        }}>
          {error}
        </div>
      )}

      {progressInfo && (
        <div style={{ fontWeight: 'bold', marginBottom: '20px', padding: '10px 18px', backgroundColor: '#fff', border: '3px solid #000', boxShadow: '4px 4px 0px #000' }}>
          {progressInfo}
        </div>
      )}

      {tracks.length > 0 && activePlaylist && (
        <div className="nb-card">
          <h2 style={{
            fontSize: '1.8rem',
            fontWeight: '900',
            textTransform: 'uppercase',
            marginBottom: '20px',
            marginTop: 0,
          }}>
            Tracks ({tracks.length})
          </h2>
          <div>
            {tracks.map((track, index) => (
              <div key={`${track.id || index}-${index}`} style={{
                border: '3px solid #000',
                padding: '15px',
                marginBottom: '12px',
                backgroundColor: '#f9f9f6',
                boxShadow: '4px 4px 0px #000',
                display: 'flex',
                gap: '15px',
                alignItems: 'center',
              }}>
                {track.album?.images?.[0]?.url && (
                  <img 
                    src={track.album.images[0].url} 
                    alt="" 
                    style={{ width: '50px', height: '50px', border: '2px solid #000', objectFit: 'cover', flexShrink: 0 }}
                  />
                )}
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: '900', fontSize: '1.1rem' }}>{track.name}</div>
                  <div style={{ fontSize: '0.9rem', color: '#555' }}>
                    👤 {track.artists ? track.artists.map(a => a.name).join(', ') : 'Unknown Artist'}
                  </div>
                  <div style={{ fontSize: '0.9rem', color: '#777' }}>
                    💿 {track.album ? track.album.name : (track.show ? track.show.name : 'Unknown Album')}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// === Callback Handler ===
function CallbackHandler() {
  const navigate = useNavigate();

  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const code = urlParams.get('code');
    const state = urlParams.get('state'); // Need state for session mapping
    if (code) {
      // 临时代理：前端收到 code 后，瞬间重定向给后端，欺骗 Spotify 的重定向校验
      window.location.href = `http://localhost:8000/auth/callback?code=${code}&state=${state}`;
    } else {
      navigate('/', { replace: true });
    }
  }, [navigate]);

  return (
    <div className="page-container">
      <div className="nb-card" style={{ textAlign: 'center', padding: '60px' }}>
        <div style={{ fontSize: '2rem', fontWeight: '900' }}>⏳</div>
        <div style={{ fontWeight: '700', marginTop: '12px' }}>Authenticating...</div>
      </div>
    </div>
  );
}

// === Main App with Navigation ===
export default function App() {
  const location = useLocation();
  const { t, lang, switchLang, LANG_LABELS } = useI18n();

  return (
    <div>
      {/* Navigation Bar */}
      <nav className="nav-bar">
        <NavLink to="/" className="nav-brand">
          {t.brand}
        </NavLink>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div className="nav-links">
            <NavLink to="/" end className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              {t.navFetcher}
            </NavLink>
            <NavLink to="/database" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              {t.navDatabase}
            </NavLink>
          </div>
          {/* Language Switcher */}
          <div style={{ display: 'flex', gap: '3px', border: '2px solid #FFE600', borderRadius: 0 }}>
            {Object.entries(LANG_LABELS).map(([code, label]) => (
              <button
                key={code}
                onClick={() => switchLang(code)}
                style={{
                  padding: '4px 10px',
                  fontSize: '0.8rem',
                  fontWeight: 800,
                  fontFamily: 'inherit',
                  border: 'none',
                  cursor: 'pointer',
                  background: lang === code ? '#FFE600' : 'transparent',
                  color: lang === code ? '#000' : '#aaa',
                  transition: 'all 0.15s',
                }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </nav>

      {/* Routes */}
      <Routes>
        <Route path="/" element={<Navigate to="/host" replace />} />
        <Route path="/host" element={<HostDashboard />} />
        <Route path="/join/:sessionId" element={<GuestEntry />} />
        <Route path="/guest-success" element={<GuestSuccess />} />
        <Route path="/guest/:guestId" element={<GuestPlaylistSelect />} />
        <Route path="/callback" element={<CallbackHandler />} />
        <Route path="/database" element={<DatabaseView />} />
      </Routes>
    </div>
  );
}
