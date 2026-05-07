const BASE = import.meta.env.VITE_API_URL

async function jsonOrThrow(response) {
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const message = data?.detail || data?.message || response.statusText
    throw new Error(message)
  }
  return data
}

export const api = {
  createSession: (name, genreSeeds) =>
    fetch(`${BASE}/host/session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, genre_seeds: genreSeeds })
    }).then(jsonOrThrow),

  getSession: (sessionId) =>
    fetch(`${BASE}/host/session/${sessionId}`).then(jsonOrThrow),

  closeSession: (sessionId) =>
    fetch(`${BASE}/host/session/${sessionId}`, { method: 'DELETE' }).then(jsonOrThrow),

  getRecommendations: (sessionId) =>
    fetch(`${BASE}/recommendations/${sessionId}`).then(jsonOrThrow),

  refreshRecommendations: (sessionId) =>
    fetch(`${BASE}/recommendations/${sessionId}/refresh`, { method: 'POST' }).then(jsonOrThrow),

  guestLoginUrl: (sessionId) =>
    `${BASE}/auth/login?session_id=${sessionId}`,

  getGuestPlaylists: (guestId) =>
    fetch(`${BASE}/guest/${guestId}/playlists`).then(jsonOrThrow),

  submitPlaylists: (guestId, playlistIds) =>
    fetch(`${BASE}/guest/${guestId}/playlists`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ playlist_ids: playlistIds })
    }).then(jsonOrThrow),

  getPlaylistTracks: (guestId, playlistId) =>
    fetch(`${BASE}/guest/${guestId}/playlists/${playlistId}/tracks`).then(jsonOrThrow),

  submitTracks: (guestId, tracks) =>
    fetch(`${BASE}/guest/${guestId}/tracks`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tracks })
    }).then(jsonOrThrow),
}

export const adminApi = {
  getSessions: () =>
    fetch(`${BASE}/admin/sessions`).then(jsonOrThrow),
  getGuests: (sessionId) =>
    fetch(`${BASE}/admin/guests${sessionId ? '?session_id='+sessionId : ''}`).then(jsonOrThrow),
  getTracks: (guestId) =>
    fetch(`${BASE}/admin/tracks${guestId ? '?guest_id='+guestId : ''}`).then(jsonOrThrow),
  getRecommendations: (sessionId) =>
    fetch(`${BASE}/admin/recommendations${sessionId ? '?session_id='+sessionId : ''}`).then(jsonOrThrow),
  deleteSession: (id) =>
    fetch(`${BASE}/admin/sessions/${id}`, {method:'DELETE'}).then(jsonOrThrow),
  deleteGuest: (id) =>
    fetch(`${BASE}/admin/guests/${id}`, {method:'DELETE'}).then(jsonOrThrow),
  deleteTrack: (id) =>
    fetch(`${BASE}/admin/tracks/${id}`, {method:'DELETE'}).then(jsonOrThrow),
}
