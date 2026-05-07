/**
 * enrichment.js — 第三方 API 元数据增强模块
 * 数据源: Last.fm, MusicBrainz, Spotify Artist
 */

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ============================================================
// Last.fm API
// ============================================================

/**
 * 获取歌曲标签 (track.getTopTags)
 */
export const lastfmGetTrackTags = async (apiKey, artist, track) => {
  try {
    const url = `https://ws.audioscrobbler.com/2.0/?method=track.getTopTags&artist=${encodeURIComponent(artist)}&track=${encodeURIComponent(track)}&api_key=${apiKey}&format=json`;
    const res = await fetch(url);
    if (!res.ok) return [];
    const data = await res.json();
    if (data.toptags?.tag) {
      return data.toptags.tag.slice(0, 10).map((t) => ({
        name: t.name,
        count: parseInt(t.count) || 0,
      }));
    }
    return [];
  } catch { return []; }
};

/**
 * 获取歌曲信息 (track.getInfo) — 播放次数、听众数
 */
export const lastfmGetTrackInfo = async (apiKey, artist, track) => {
  try {
    const url = `https://ws.audioscrobbler.com/2.0/?method=track.getInfo&artist=${encodeURIComponent(artist)}&track=${encodeURIComponent(track)}&api_key=${apiKey}&format=json`;
    const res = await fetch(url);
    if (!res.ok) return null;
    const data = await res.json();
    if (data.track) {
      return {
        playcount: parseInt(data.track.playcount) || 0,
        listeners: parseInt(data.track.listeners) || 0,
        tags: (data.track.toptags?.tag || []).slice(0, 10).map((t) => t.name),
        duration: parseInt(data.track.duration) || 0,
        url: data.track.url || '',
      };
    }
    return null;
  } catch { return null; }
};

/**
 * 获取相似歌曲 (track.getSimilar)
 */
export const lastfmGetSimilarTracks = async (apiKey, artist, track, limit = 5) => {
  try {
    const url = `https://ws.audioscrobbler.com/2.0/?method=track.getSimilar&artist=${encodeURIComponent(artist)}&track=${encodeURIComponent(track)}&api_key=${apiKey}&limit=${limit}&format=json`;
    const res = await fetch(url);
    if (!res.ok) return [];
    const data = await res.json();
    if (data.similartracks?.track) {
      return data.similartracks.track.map((t) => ({
        name: t.name,
        artist: t.artist?.name || '',
        match: parseFloat(t.match) || 0,
        url: t.url || '',
      }));
    }
    return [];
  } catch { return []; }
};

/**
 * 获取艺术家标签 (artist.getTopTags)
 */
export const lastfmGetArtistTags = async (apiKey, artist) => {
  try {
    const url = `https://ws.audioscrobbler.com/2.0/?method=artist.getTopTags&artist=${encodeURIComponent(artist)}&api_key=${apiKey}&format=json`;
    const res = await fetch(url);
    if (!res.ok) return [];
    const data = await res.json();
    if (data.toptags?.tag) {
      return data.toptags.tag.slice(0, 10).map((t) => ({
        name: t.name,
        count: parseInt(t.count) || 0,
      }));
    }
    return [];
  } catch { return []; }
};

// ============================================================
// MusicBrainz API
// ============================================================

const MB_BASE = 'https://musicbrainz.org/ws/2';
const MB_HEADERS = {
  'Accept': 'application/json',
  'User-Agent': 'CrowdBeat/1.0 (https://github.com/crowdbeat)',
};

/**
 * 通过 ISRC 查询录音信息 (genres + tags)
 */
export const mbLookupByISRC = async (isrc) => {
  if (!isrc) return null;
  try {
    // Step 1: ISRC → recording ID (no inc params allowed on /isrc/)
    const isrcUrl = `${MB_BASE}/isrc/${isrc}?fmt=json`;
    const isrcRes = await fetch(isrcUrl, { headers: MB_HEADERS });
    if (!isrcRes.ok) return null;
    const isrcData = await isrcRes.json();
    const mbid = isrcData.recordings?.[0]?.id;
    if (!mbid) return null;

    // Step 2: recording lookup with genres, tags, and deep relations
    await new Promise(r => setTimeout(r, 1100)); // MusicBrainz rate limit: 1 req/sec
    const recUrl = `${MB_BASE}/recording/${mbid}?inc=genres+tags+releases+artist-rels+work-rels+work-level-rels+url-rels+ratings&fmt=json`;
    const recRes = await fetch(recUrl, { headers: MB_HEADERS });
    if (!recRes.ok) return null;
    const recording = await recRes.json();

    // Parse relations
    const relations = recording.relations || [];
    const producers = relations.filter(r => r.type === 'producer' && r.artist).map(r => r.artist.name);
    const engineers = relations.filter(r => r.type === 'engineer' && r.artist).map(r => r.artist.name);
    const links = relations.filter(r => r['target-type'] === 'url' && r.url).map(r => r.url.resource);

    let composers = [];
    let lyricists = [];
    relations.filter(r => r['target-type'] === 'work' && r.work).forEach(r => {
      if (r.work.relations) {
        r.work.relations.forEach(wr => {
          if (wr.type === 'composer' && wr.artist) composers.push(wr.artist.name);
          if (wr.type === 'lyricist' && wr.artist) lyricists.push(wr.artist.name);
        });
      }
    });

    return {
      mbid: recording.id || mbid,
      genres: (recording.genres || []).map((g) => g.name),
      tags: (recording.tags || []).sort((a, b) => (b.count || 0) - (a.count || 0)).slice(0, 10).map((t) => t.name),
      firstRelease: recording['first-release-date'] || '',
      country: recording.releases?.[0]?.country || '',
      disambiguation: recording.disambiguation || '',
      // New fields
      rating: recording.rating?.value || null,
      producers: [...new Set(producers)],
      engineers: [...new Set(engineers)],
      composers: [...new Set(composers)],
      lyricists: [...new Set(lyricists)],
      links: links
    };
  } catch { return null; }
};

// ============================================================
// Spotify Artist API
// ============================================================

/**
 * 获取单个艺术家详情 (genres + followers)
 */
export const spotifyGetArtist = async (token, artistId) => {
  if (!artistId || !token) return null;
  try {
    const res = await fetch(`https://api.spotify.com/v1/artists/${artistId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.status === 429) {
      const retryAfter = res.headers.get('Retry-After');
      return { _retry: true, _delay: retryAfter ? parseInt(retryAfter) * 1000 : 2000 };
    }
    if (!res.ok) return null;
    const data = await res.json();
    return {
      genres: data.genres || [],
      followers: data.followers?.total || 0,
      artistPopularity: data.popularity || 0,
      artistImage: data.images?.[0]?.url || '',
    };
  } catch { return null; }
};

// ============================================================
// 批量增强编排器
// ============================================================

/**
 * 对一批歌曲进行全量元数据增强
 * @param {Array} songs - 歌曲数组（已在 IndexedDB 中的数据）
 * @param {Object} options - { lastfmApiKey, spotifyToken, sources: ['lastfm','musicbrainz','spotify'], onProgress }
 * @returns {Array} 增强后的歌曲数组
 */
export const enrichSongs = async (songs, options = {}) => {
  const {
    lastfmApiKey = '',
    spotifyToken = '',
    sources = ['lastfm', 'musicbrainz', 'spotify'],
    onProgress = () => {},
  } = options;

  const total = songs.length;
  const enriched = [...songs];

  // Cache: 避免重复请求同一艺术家
  const artistCache = {};

  for (let i = 0; i < total; i++) {
    const song = { ...enriched[i] };
    const mainArtist = (song.artists || [])[0] || '';
    const mainArtistId = (song.artistIds || [])[0] || '';
    const progress = Math.round(((i + 1) / total) * 100);

    onProgress({
      current: i + 1,
      total,
      percent: progress,
      songName: song.name,
      stage: 'processing',
    });

    // --- Last.fm ---
    if (sources.includes('lastfm') && lastfmApiKey && mainArtist) {
      try {
        // track.getInfo (includes playcount + listeners + tags)
        const info = await lastfmGetTrackInfo(lastfmApiKey, mainArtist, song.name);
        if (info) {
          song.lastfmPlaycount = info.playcount;
          song.lastfmListeners = info.listeners;
          song.lastfmUrl = info.url;
          if (info.tags.length > 0) {
            song.lastfmTags = info.tags;
          }
        }

        // track.getTopTags (more detailed)
        if (!song.lastfmTags || song.lastfmTags.length === 0) {
          const tags = await lastfmGetTrackTags(lastfmApiKey, mainArtist, song.name);
          if (tags.length > 0) {
            song.lastfmTags = tags.map((t) => t.name);
          }
          await sleep(200);
        }

        // track.getSimilar
        const similar = await lastfmGetSimilarTracks(lastfmApiKey, mainArtist, song.name, 5);
        if (similar.length > 0) {
          song.similarTracks = similar;
        }

        // artist.getTopTags (cached per artist)
        if (!artistCache[mainArtist]?.lastfmTags) {
          const artistTags = await lastfmGetArtistTags(lastfmApiKey, mainArtist);
          if (!artistCache[mainArtist]) artistCache[mainArtist] = {};
          artistCache[mainArtist].lastfmTags = artistTags.map((t) => t.name);
          await sleep(300);
        }
        song.artistTags = artistCache[mainArtist].lastfmTags || [];

        await sleep(300); // rate limit
      } catch (err) {
        console.warn(`Last.fm error for "${song.name}":`, err);
      }
    }

    // --- MusicBrainz ---
    if (sources.includes('musicbrainz') && song.isrc) {
      try {
        const mb = await mbLookupByISRC(song.isrc);
        if (mb) {
          song.mbGenres = mb.genres;
          song.mbTags = mb.tags;
          song.mbCountry = mb.country;
          song.mbFirstRelease = mb.firstRelease;
          song.mbid = mb.mbid;
          song.mbRating = mb.rating;
          song.mbProducers = mb.producers;
          song.mbEngineers = mb.engineers;
          song.mbComposers = mb.composers;
          song.mbLyricists = mb.lyricists;
          song.mbLinks = mb.links;
        }
        await sleep(1100); // MusicBrainz: 1 req/sec
      } catch (err) {
        console.warn(`MusicBrainz error for "${song.name}":`, err);
      }
    }

    // --- Spotify Artist ---
    if (sources.includes('spotify') && spotifyToken && mainArtistId) {
      try {
        if (!artistCache[mainArtistId]?.spotifyData) {
          let artistData = await spotifyGetArtist(spotifyToken, mainArtistId);
          // Handle rate limit retry
          if (artistData?._retry) {
            await sleep(artistData._delay);
            artistData = await spotifyGetArtist(spotifyToken, mainArtistId);
          }
          if (!artistCache[mainArtistId]) artistCache[mainArtistId] = {};
          artistCache[mainArtistId].spotifyData = artistData;
          await sleep(200);
        }
        const cached = artistCache[mainArtistId]?.spotifyData;
        if (cached && !cached._retry) {
          song.artistGenres = cached.genres;
          song.artistFollowers = cached.followers;
          song.artistPopularity = cached.artistPopularity;
          song.artistImage = cached.artistImage;
        }
      } catch (err) {
        console.warn(`Spotify Artist error for "${song.name}":`, err);
      }
    }

    enriched[i] = song;
  }

  onProgress({ current: total, total, percent: 100, songName: '', stage: 'done' });
  return enriched;
};
