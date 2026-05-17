const BASE = import.meta.env.VITE_API_URL || `http://${window.location.hostname}:8000`;

export const api = {
  // 场次
  createSession: (name, genreSeeds) =>
    fetch(`${BASE}/host/session`, {
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
    fetch(`${BASE}/host/session/${sessionId}`).then(r => {
      if (!r.ok) throw new Error(r.statusText)
      return r.json()
    }),

  closeSession: (sessionId) =>
    fetch(`${BASE}/host/session/${sessionId}`, { method: 'DELETE' }).then(r => r.json()),

  refreshRecommendations: (sessionId) =>
    fetch(`${BASE}/recommendations/${sessionId}/refresh`, { method: 'POST' }).then(r => r.json()),

  getRecommendations: (sessionId) =>
    fetch(`${BASE}/recommendations/${sessionId}`).then(r => r.json()),

  // DJ Spotify (server-side OAuth)
  djLogin: (sessionId) =>
    `${BASE}/auth/dj/login?session_id=${sessionId}`,

  createPlaylist: (sessionId, playlistName) =>
    fetch(`${BASE}/host/session/${sessionId}/playlist/create`, {
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
    fetch(`${BASE}/host/session/${sessionId}/playlist/add-track`, {
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
    fetch(`${BASE}/host/session/${sessionId}/playlist/tracks`).then(r => r.json()),

  // Guest
  guestLoginUrl: (sessionId) =>
    `${BASE}/auth/login?session_id=${sessionId}`,

  joinManual: (sessionId, displayName, email) =>
    fetch(`${BASE}/guest/manual`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, display_name: displayName, email })
    }).then(async r => {
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || r.statusText);
      }
      return r.json();
    }),

  getGuestPlaylists: (guestId) =>
    fetch(`${BASE}/guest/${guestId}/playlists`).then(r => {
      if (!r.ok) throw new Error(r.statusText)
      return r.json()
    }),

  submitPlaylists: (guestId, playlistIds) =>
    fetch(`${BASE}/guest/${guestId}/playlists`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ playlist_ids: playlistIds })
    }).then(r => {
      if (!r.ok) throw new Error(r.statusText)
      return r.json()
    }),

  getPlaylistTracks: (guestId, playlistId) =>
    fetch(`${BASE}/guest/${guestId}/playlists/${playlistId}/tracks`).then(r => {
      if (!r.ok) throw new Error(r.statusText)
      return r.json()
    }),

  submitTracks: (guestId, tracks) =>
    fetch(`${BASE}/guest/${guestId}/tracks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tracks })
    }).then(r => {
      if (!r.ok) throw new Error(r.statusText)
      return r.json()
    }),

  // Admin
  admin: {
    getSessions: () => fetch(`${BASE}/admin/sessions`).then(r => r.json()),
    getGuests: (sid) => fetch(`${BASE}/admin/guests${sid ? '?session_id=' + sid : ''}`).then(r => r.json()),
    getTracks: (gid, sid) => {
      const params = new URLSearchParams();
      if (gid) params.append('guest_id', gid);
      if (sid) params.append('session_id', sid);
      const qs = params.toString() ? `?${params.toString()}` : '';
      return fetch(`${BASE}/admin/tracks${qs}`).then(r => r.json());
    },
    getRecommendations: (sid) => fetch(`${BASE}/admin/recommendations${sid ? '?session_id=' + sid : ''}`).then(r => r.json()),
    getPlaylistTracks: (sid) => fetch(`${BASE}/admin/playlist_tracks${sid ? '?session_id=' + sid : ''}`).then(r => r.json()),
    deleteSession: (id) => fetch(`${BASE}/admin/sessions/${id}`, { method: 'DELETE' }).then(r => r.json()),
    deleteGuest: (id) => fetch(`${BASE}/admin/guests/${id}`, { method: 'DELETE' }).then(r => r.json()),
    deleteTrack: (id) => fetch(`${BASE}/admin/tracks/${id}`, { method: 'DELETE' }).then(r => r.json()),
  }
}

// Legacy export for backward compatibility (HostDashboard, DatabaseView etc.)
export const adminApi = api.admin
