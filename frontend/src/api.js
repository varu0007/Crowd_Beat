export const API_BASE = import.meta.env.VITE_API_URL || window.location.origin;
export const WS_BASE = (import.meta.env.VITE_WS_URL || API_BASE)
  .replace(/^http:\/\//i, 'ws://')
  .replace(/^https:\/\//i, 'wss://')
  .replace(/\/$/, '');

export const api = {
  // åœºæ¬¡
  createSession: (name, genreSeeds) =>
    fetch(`${API_BASE}/host/session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, genre_seeds: genreSeeds })
    }).then(async r => {
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || r.statusText);
      }
      return r.json();
    }),

  getSession: (sessionId) =>
    fetch(`${API_BASE}/host/session/${sessionId}`).then(r => {
      if (!r.ok) throw new Error(r.statusText)
      return r.json()
    }),

  closeSession: (sessionId) =>
    fetch(`${API_BASE}/host/session/${sessionId}`, { method: 'DELETE' }).then(r => r.json()),

  refreshRecommendations: (sessionId) =>
    fetch(`${API_BASE}/recommendations/${sessionId}/refresh`, { method: 'POST' }).then(r => r.json()),

  getRecommendations: (sessionId) =>
    fetch(`${API_BASE}/recommendations/${sessionId}`).then(r => r.json()),

  // DJ Spotify (server-side OAuth)
  djLogin: (sessionId) =>
    `${API_BASE}/auth/dj/login?session_id=${sessionId}`,

  // Guest Spotify OAuth that also captures username + email via OAuth state
  guestLoginWithProfileUrl: (sessionId, profile) => {
    const params = new URLSearchParams();
    params.set('session_id', sessionId);
    if (profile?.username) params.set('username', profile.username);
    if (profile?.email) params.set('email', profile.email);
    return `${API_BASE}/auth/login_with_profile?${params.toString()}`;
  },


  createPlaylist: (sessionId, playlistName) =>
    fetch(`${API_BASE}/host/session/${sessionId}/playlist/create`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ playlist_name: playlistName })
    }).then(async r => {
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        let msg = err.detail;
        if (Array.isArray(msg)) msg = msg[0].msg; // Handle Pydantic validation errors
        throw new Error(msg || r.statusText);
      }
      return r.json();
    }),

  addTrackToPlaylist: (sessionId, trackId, trackName, artistName) =>
    fetch(`${API_BASE}/host/session/${sessionId}/playlist/add-track`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ track_id: trackId, track_name: trackName || "Unknown", artist_name: artistName || "Unknown" })
    }).then(async r => {
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        let msg = err.detail;
        if (Array.isArray(msg)) msg = msg[0].msg; // Handle Pydantic validation errors
        throw new Error(msg || r.statusText);
      }
      return r.json();
    }),

  getDjPlaylistTracks: (sessionId) =>
    fetch(`${API_BASE}/host/session/${sessionId}/playlist/tracks`).then(r => r.json()),

  // Guest
  guestLoginUrl: (sessionId) =>
    `${API_BASE}/auth/login?session_id=${sessionId}`,

  // Guest profile CSV rows for download
  getGuestProfileCsvRows: (guestId) =>
    fetch(`${API_BASE}/guest/${guestId}/profile-csv`).then(r => r.json()),



  getGuestPlaylists: (guestId) =>
    fetch(`${API_BASE}/guest/${guestId}/playlists`).then(r => {
      if (!r.ok) throw new Error(r.statusText)
      return r.json()
    }),

  submitPlaylists: (guestId, playlistIds) =>
    fetch(`${API_BASE}/guest/${guestId}/playlists`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ playlist_ids: playlistIds })
    }).then(r => {
      if (!r.ok) throw new Error(r.statusText)
      return r.json()
    }),

  getPlaylistTracks: (guestId, playlistId) =>
    fetch(`${API_BASE}/guest/${guestId}/playlists/${playlistId}/tracks`).then(r => {
      if (!r.ok) throw new Error(r.statusText)
      return r.json()
    }),

  submitTracks: (guestId, tracks) =>
    fetch(`${API_BASE}/guest/${guestId}/tracks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tracks })
    }).then(r => {
      if (!r.ok) throw new Error(r.statusText)
      return r.json()
    }),

  // Admin
  admin: {
    getSessions: () => fetch(`${API_BASE}/admin/sessions`).then(r => r.json()),
    getGuests: (sid) => fetch(`${API_BASE}/admin/guests${sid ? '?session_id=' + sid : ''}`).then(r => r.json()),
    getTracks: (gid, sid) => {
      const params = new URLSearchParams();
      if (gid) params.append('guest_id', gid);
      if (sid) params.append('session_id', sid);
      const qs = params.toString() ? `?${params.toString()}` : '';
      return fetch(`${API_BASE}/admin/tracks${qs}`).then(r => r.json());
    },
    getRecommendations: (sid) => fetch(`${API_BASE}/admin/recommendations${sid ? '?session_id=' + sid : ''}`).then(r => r.json()),
    getPlaylistTracks: (sid) => fetch(`${API_BASE}/admin/playlist_tracks${sid ? '?session_id=' + sid : ''}`).then(r => r.json()),
    deleteSession: (id) => fetch(`${API_BASE}/admin/sessions/${id}`, { method: 'DELETE' }).then(r => r.json()),
    deleteGuest: (id) => fetch(`${API_BASE}/admin/guests/${id}`, { method: 'DELETE' }).then(r => r.json()),
    deleteTrack: (id) => fetch(`${API_BASE}/admin/tracks/${id}`, { method: 'DELETE' }).then(r => r.json()),
  }
}

// Legacy export for backward compatibility (HostDashboard, DatabaseView etc.)
export const adminApi = api.admin
