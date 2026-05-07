const BASE = import.meta.env.VITE_API_URL

export const api = {
  createSession: (name, genreSeeds) =>
    fetch(`${BASE}/host/session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, genre_seeds: genreSeeds })
    }).then(r => { if (!r.ok) throw new Error(r.statusText); return r.json() }),

  getSession: (sessionId) =>
    fetch(`${BASE}/host/session/${sessionId}`).then(r => r.json()),

  closeSession: (sessionId) =>
    fetch(`${BASE}/host/session/${sessionId}`, { method: 'DELETE' }).then(r => r.json()),

  getRecommendations: (sessionId) =>
    fetch(`${BASE}/recommendations/${sessionId}`).then(r => r.json()),

  refreshRecommendations: (sessionId) =>
    fetch(`${BASE}/recommendations/${sessionId}/refresh`, { method: 'POST' }).then(r => r.json()),

  guestLoginUrl: (sessionId) =>
    `${BASE}/auth/login?session_id=${sessionId}`,

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
}

export const adminApi = {
  getSessions: () =>
    fetch(`${BASE}/admin/sessions`).then(r => r.json()),
  getGuests: (sessionId) =>
    fetch(`${BASE}/admin/guests${sessionId ? '?session_id='+sessionId : ''}`).then(r => r.json()),
  getTracks: (guestId) =>
    fetch(`${BASE}/admin/tracks${guestId ? '?guest_id='+guestId : ''}`).then(r => r.json()),
  getRecommendations: (sessionId) =>
    fetch(`${BASE}/admin/recommendations${sessionId ? '?session_id='+sessionId : ''}`).then(r => r.json()),
  deleteSession: (id) =>
    fetch(`${BASE}/admin/sessions/${id}`, {method:'DELETE'}).then(r => r.json()),
  deleteGuest: (id) =>
    fetch(`${BASE}/admin/guests/${id}`, {method:'DELETE'}).then(r => r.json()),
  deleteTrack: (id) =>
    fetch(`${BASE}/admin/tracks/${id}`, {method:'DELETE'}).then(r => r.json()),
}
