import { openDB } from 'idb';

const DB_NAME = 'CrowdBeatDB';
const DB_VERSION = 3;
const STORE_NAME = 'songs';

/**
 * 初始化 IndexedDB 数据库
 */
export const initDB = async () => {
  return openDB(DB_NAME, DB_VERSION, {
    upgrade(db, oldVersion, newVersion, transaction) {
      let store;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        store = db.createObjectStore(STORE_NAME, { keyPath: 'id' });
        store.createIndex('name', 'name', { unique: false });
        store.createIndex('album', 'album', { unique: false });
        store.createIndex('playlist', 'playlist', { unique: false });
        store.createIndex('addedAt', 'addedAt', { unique: false });
        store.createIndex('popularity', 'popularity', { unique: false });
        store.createIndex('releaseDate', 'releaseDate', { unique: false });
      } else {
        // 升级: 通过 transaction 访问已有 store 添加索引
        store = transaction.objectStore(STORE_NAME);
        if (oldVersion < 2) {
          if (!store.indexNames.contains('popularity')) store.createIndex('popularity', 'popularity', { unique: false });
          if (!store.indexNames.contains('releaseDate')) store.createIndex('releaseDate', 'releaseDate', { unique: false });
        }
        // v3: no new indexes needed, enrichment fields are just properties
      }
    },
  });
};

/**
 * 获取所有歌曲
 */
export const getAllSongs = async () => {
  const db = await initDB();
  return db.getAll(STORE_NAME);
};

/**
 * 根据 ID 获取歌曲
 */
export const getSongById = async (id) => {
  const db = await initDB();
  return db.get(STORE_NAME, id);
};

/**
 * 新增单首歌曲
 */
export const addSong = async (song) => {
  const db = await initDB();
  const songData = {
    ...song,
    addedAt: song.addedAt || new Date().toISOString(),
  };
  return db.put(STORE_NAME, songData);
};

/**
 * 批量导入歌曲
 */
export const addSongsBatch = async (songs) => {
  const db = await initDB();
  const tx = db.transaction(STORE_NAME, 'readwrite');
  const now = new Date().toISOString();

  const promises = songs.map((song) => {
    const songData = {
      ...song,
      addedAt: song.addedAt || now,
    };
    return tx.store.put(songData);
  });

  promises.push(tx.done);
  await Promise.all(promises);
  return songs.length;
};

/**
 * 更新歌曲
 */
export const updateSong = async (song) => {
  const db = await initDB();
  return db.put(STORE_NAME, song);
};

/**
 * 删除歌曲
 */
export const deleteSong = async (id) => {
  const db = await initDB();
  return db.delete(STORE_NAME, id);
};

/**
 * 批量删除
 */
export const deleteSongsBatch = async (ids) => {
  const db = await initDB();
  const tx = db.transaction(STORE_NAME, 'readwrite');
  const promises = ids.map((id) => tx.store.delete(id));
  promises.push(tx.done);
  await Promise.all(promises);
  return ids.length;
};

/**
 * 搜索歌曲 (模糊匹配 name, artists, album)
 */
export const searchSongs = async (query) => {
  const all = await getAllSongs();
  if (!query || query.trim() === '') return all;

  const lowerQuery = query.toLowerCase().trim();
  return all.filter((song) => {
    const nameMatch = (song.name || '').toLowerCase().includes(lowerQuery);
    const artistMatch = (song.artists || []).some((a) =>
      a.toLowerCase().includes(lowerQuery)
    );
    const albumMatch = (song.album || '').toLowerCase().includes(lowerQuery);
    return nameMatch || artistMatch || albumMatch;
  });
};

/**
 * 获取统计信息
 */
export const getStats = async () => {
  const all = await getAllSongs();
  const playlists = [...new Set(all.map((s) => s.playlist).filter(Boolean))];
  const artists = [...new Set(all.flatMap((s) => s.artists || []))];
  const albums = [...new Set(all.map((s) => s.album).filter(Boolean))];
  const avgPopularity = all.length > 0
    ? Math.round(all.reduce((sum, s) => sum + (s.popularity || 0), 0) / all.length)
    : 0;
  const avgDuration = all.length > 0
    ? Math.round(all.reduce((sum, s) => sum + (s.duration || 0), 0) / all.length)
    : 0;
  const explicitCount = all.filter((s) => s.explicit).length;

  return {
    totalSongs: all.length,
    totalPlaylists: playlists.length,
    totalArtists: artists.length,
    totalAlbums: albums.length,
    avgPopularity,
    avgDuration,
    explicitCount,
    playlists,
  };
};

/**
 * 将 Spotify Track 对象转换为数据库 Song 对象
 * 尽可能提取所有可用的元数据字段
 */
export const spotifyTrackToSong = (track, playlistName = '', addedAtPlaylist = '') => {
  return {
    // === 基本信息 ===
    id: track.id || `local_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    name: track.name || 'Unknown',
    artists: track.artists ? track.artists.map((a) => a.name) : [],
    artistIds: track.artists ? track.artists.map((a) => a.id) : [],
    artistUrls: track.artists ? track.artists.map((a) => a.external_urls?.spotify || '') : [],

    // === 专辑信息 ===
    album: track.album ? track.album.name : (track.show ? track.show.name : ''),
    albumId: track.album?.id || '',
    albumType: track.album?.album_type || '', // album, single, compilation
    albumImage: track.album?.images?.[0]?.url || '',
    albumImageSmall: track.album?.images?.[2]?.url || track.album?.images?.[1]?.url || '',
    albumUrl: track.album?.external_urls?.spotify || '',
    albumArtists: track.album?.artists ? track.album.artists.map((a) => a.name) : [],
    albumTotalTracks: track.album?.total_tracks || 0,
    releaseDate: track.album?.release_date || '',
    releaseDatePrecision: track.album?.release_date_precision || '', // year, month, day

    // === 曲目信息 ===
    duration: track.duration_ms || 0,
    popularity: track.popularity || 0,
    explicit: track.explicit || false,
    trackNumber: track.track_number || 0,
    discNumber: track.disc_number || 0,
    isLocal: track.is_local || false,
    previewUrl: track.preview_url || '',

    // === 外部标识 ===
    spotifyUrl: track.external_urls?.spotify || '',
    spotifyUri: track.uri || '',
    isrc: track.external_ids?.isrc || '',
    ean: track.external_ids?.ean || '',
    upc: track.external_ids?.upc || '',

    // === 可用市场 ===
    availableMarkets: track.available_markets || [],
    availableMarketsCount: (track.available_markets || []).length,

    // === 播放列表来源 ===
    playlist: playlistName,
    addedAtPlaylist: addedAtPlaylist, // 添加到播放列表的时间

    // === Audio Features (由 Spotify API 单独获取后合并) ===
    danceability: null,
    energy: null,
    key: null,
    loudness: null,
    mode: null,
    speechiness: null,
    acousticness: null,
    instrumentalness: null,
    liveness: null,
    valence: null,
    tempo: null,
    timeSignature: null,

    // === Last.fm 增强数据 ===
    lastfmTags: [],          // 歌曲标签 ["indie rock", "chill", ...]
    lastfmPlaycount: 0,      // 全球播放次数
    lastfmListeners: 0,      // 听众数
    lastfmUrl: '',           // Last.fm 页面链接
    similarTracks: [],       // [{name, artist, match, url}]
    artistTags: [],          // 艺术家标签

    // === MusicBrainz 增强数据 ===
    mbGenres: [],            // 官方流派
    mbTags: [],              // 社区标签
    mbCountry: '',           // 发行国家
    mbFirstRelease: '',      // 最早发行日期
    mbid: '',                // MusicBrainz ID

    // === Spotify Artist 增强数据 ===
    artistGenres: [],        // Spotify 艺术家流派
    artistFollowers: 0,      // 粉丝数
    artistPopularity: 0,     // 艺术家流行度
    artistImage: '',         // 艺术家头像

    // === 增强状态 ===
    enriched: false,         // 是否已增强
    enrichedAt: '',          // 增强时间

    // === 用户自定义 ===
    notes: '',
  };
};

/**
 * 音调映射表 (Pitch Class → 音名)
 */
export const KEY_NAMES = ['C', 'C♯/D♭', 'D', 'D♯/E♭', 'E', 'F', 'F♯/G♭', 'G', 'G♯/A♭', 'A', 'A♯/B♭', 'B'];

/**
 * 将 Audio Features 合并到 Song 对象中
 */
export const mergeAudioFeatures = (song, features) => {
  if (!features) return song;
  return {
    ...song,
    danceability: features.danceability ?? null,
    energy: features.energy ?? null,
    key: features.key ?? null,
    loudness: features.loudness ?? null,
    mode: features.mode ?? null, // 0 = minor, 1 = major
    speechiness: features.speechiness ?? null,
    acousticness: features.acousticness ?? null,
    instrumentalness: features.instrumentalness ?? null,
    liveness: features.liveness ?? null,
    valence: features.valence ?? null,
    tempo: features.tempo ?? null,
    timeSignature: features.time_signature ?? null,
  };
};
