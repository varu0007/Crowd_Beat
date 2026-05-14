import React, { createContext, useContext, useState } from 'react';
import {
  Headphones, Database, Heart, Save, Hourglass, Download, RefreshCw,
  Sliders, Snowflake, Flame, CheckCircle, Rocket, Square, Star,
  ClipboardCopy, Smartphone, Music
} from 'lucide-react';

const iconStyle = { marginRight: '6px', verticalAlign: 'middle', display: 'inline-block', width: '1.2em', height: '1.2em' };

const baseTranslations = {
  brand: 'CrowdBeat',
  navFetcher: <><Headphones style={iconStyle} /> Fetcher</>,
  navDatabase: <><Database style={iconStyle} /> Database</>,

  fetcherTitle: 'Spotify Fetcher',
  authRequired: 'Authentication required to access your Spotify data.',
  connectSpotify: 'Connect Spotify',
  authenticated: <><CheckCircle style={iconStyle} /> Authenticated</>,
  logOut: 'Log Out',
  yourLibrary: 'Your Library',
  likedSongs: <><Heart style={iconStyle} /> Liked Songs</>,
  back: 'Back',
  saveToDB: <><Save style={iconStyle} /> Save to Database</>,
  saving: <><Hourglass style={iconStyle} className="animate-pulse" /> Saving...</>,
  downloadJSON: <><Download style={iconStyle} /> Download JSON</>,
  inspecting: 'Inspecting',
  songs: 'songs',
  artists: 'artists',
  artist: 'Artist',
  album: 'Album',

  dbLoadFailed: (msg) => `Load failed: ${msg}`,
  dbConfirmDeleteSession: 'Delete this session and all its data?',
  dbDeleteFailed: (msg) => `Delete failed: ${msg}`,
  dbConfirmDeleteGuest: 'Delete this guest and all their tracks?',
  dbConfirmDeleteTrack: 'Delete this track?',
  dbRefresh: <><RefreshCw style={iconStyle} /> Refresh</>,
  dbViewingGuestsFor: (id) => <>Viewing guests for session <span style={{ color: '#00A859' }}>{id}</span></>,
  dbViewingTracksFor: (id) => <>Viewing tracks for guest <span style={{ color: '#00A859' }}>{id}</span></>,
  dbViewingRecsFor: (id) => <>Viewing recommendations for session <span style={{ color: '#00A859' }}>{id}</span></>,
  dbViewingPlaylistFor: (id) => <>Viewing playlist tracks for session <span style={{ color: '#00A859' }}>{id}</span></>,
  dbClearFilter: 'Clear Filter',
  dbClearFilterAll: 'Clear All Filters',
  dbFiltersLabel: <><Sliders style={iconStyle} /> Filters:</>,
  dbAllSessions: '-- Show All Sessions --',
  dbLoading: 'Loading...',
  dbNoData: 'No Data',
  colSessionId: 'Session ID',
  colName: 'Name',
  colStatus: 'Status',
  colGenres: 'Genre Presets',
  colCreatedAt: 'Created At',
  colGuestCount: 'Guests',
  colActions: 'Actions',
  colGuestId: 'Guest ID',
  colDisplayName: 'Display Name',
  colSpotifyUserId: 'Spotify User ID',
  colJoinedAt: 'Joined At',
  colId: 'ID',
  colTrackName: 'Track Name',
  colArtistName: 'Artist',
  colPopularity: 'Popularity',
  colDanceability: 'Danceability',
  colEnergy: 'Energy',
  colValence: 'Valence',
  colRank: 'Rank',
  colScore: 'Score',
  colColdStart: 'Cold Start',
  colGeneratedAt: 'Generated At',
  btnViewGuests: 'View Guests',
  btnViewTracks: 'View Tracks',
  btnViewPlaylist: 'View Playlist',
  btnDelete: 'Delete',
  yesColdStart: <><Snowflake style={iconStyle} /> Yes</>,

  djPlaylistTitle: 'DJ Virtual Playlist',
  prevRecs: 'Prev Recs',
  latestRecs: 'Latest Recs',
  guestsCountLabel: 'Guests',
  djNewHits: <><Flame style={{ ...iconStyle, color: '#FF4C4C' }} /> DJ New Hits</>,
  guestWishes: <><Heart style={{ ...iconStyle, color: '#00A859' }} /> Guest Wishes</>,
  addedToPlaylist: <><CheckCircle style={iconStyle} /> Added</>,
  addToPlaylist: '+ Add to Playlist',
  currentPlaylist: 'Current Playlist',
  songsCount: 'songs',
  internalPlaylist: 'Internal Playlist',
  initPlaylist: 'Initialize Playlist',
  defaultPlaylistName: "CrowdBeat - Tonight's Party",
  startMixing: 'Start Mixing',
  playlistReady: <><CheckCircle style={{ ...iconStyle, color: '#00A859' }} /> Internal playlist ready</>,
  playlistNameLabel: 'Name: ',
  playlistHint: 'Hint: Load tracks into Rekordbox or Serato based on the recommendations below.',
  recBoard: 'Recommendation Board',
  historyVersion: 'History',
  noNewHits: 'No new hit recommendations',
  noGuestWishes: 'No guest wishes',
  emptyPlaylist: 'No tracks added yet. Add tracks from the recommendation board.',
  backToLobby: 'Back to Lobby',

  homeSubtitle: 'AI Live Recommendations - Essential for DJs',
  confirmCloseSessionLobby: 'Are you sure you want to end this party? All data will be saved, but the session will be closed.',
  currentGuestsX: (n) => `Currently ${n} joined`,
  displayScreen: 'Display Screen',
  displayScreenDesc: 'Cast to a screen so guests can scan to join',
  djWorkstation: 'DJ Workstation',
  djWorkstationDesc: 'Real-time recommendation board and playlist management',
  endParty: 'End Party',

  enterSessionName: 'Please enter a session name',
  selectAtLeastOneGenre: 'Please select at least one genre preset',
  createFailed: (msg) => `Creation failed: ${msg}`,
  refreshFailed: (msg) => `Refresh failed: ${msg}`,
  confirmCloseSession: 'Are you sure you want to end this party? All guests will be disconnected.',
  closeFailed: (msg) => `Close failed: ${msg}`,
  createPartySession: 'Create Party Session',
  sessionName: 'Session Name',
  partyTonight: 'Party Tonight',
  presetGenres: 'Preset Genres (1-5)',
  creating: 'Creating...',
  startParty: <><Rocket style={iconStyle} /> Start Party</>,
  partyOngoing: 'Party Ongoing',
  endSessionBtn: <><Square style={iconStyle} /> End Session</>,
  manualRefresh: <><RefreshCw style={iconStyle} /> Manual Refresh</>,
  currentGuests: 'Current Guests:',
  wsConnected: 'Receiving live updates',
  wsDisconnected: 'WebSocket disconnected',
  currentRecommendations: 'Current Recommendations',
  coldStartNotice: <><Star style={{ ...iconStyle, color: '#FFE600' }} /> Cold Start Mode (Guests less than 5)</>,
  waitingForGuests: 'Waiting for guests...',
  waitingForGuestsDesc: 'Ask guests to scan the QR code to join. Recommendations will be generated based on their music taste.',
  matchScore: 'Match',

  copyTestLink: <><ClipboardCopy style={iconStyle} /> Copy Test Link</>,
  linkCopied: 'Link copied to clipboard!',
  scanToJoin: <><Smartphone style={iconStyle} /> Scan to join the party and share your music taste</>,
  guestsJoined: 'guests joined',
  djTonightPlaylist: <><Music style={iconStyle} /> DJ Tonight Playlist</>,
  waitingForDj: 'Waiting for the DJ to select tracks...',
  poweredBy: 'Powered by CrowdBeat - Live AI Recommendations',

  redirectingToSpotify: 'Redirecting to Spotify authorization...',
  authSuccess: 'Authorization Successful!',
  tasteAdded: 'Your music taste has been added to the party. The DJ is selecting songs for you.',

  loadTracksFailed: (msg) => `Failed to load tracks: ${msg}`,
  loadPlaylistsFailed: (msg) => `Failed to load playlists: ${msg}`,
  submitFailed: (msg) => `Submit failed: ${msg}`,
  hi: 'Hi',
  selectMusicForParty: 'Select Music for the Party',
  selectPlaylistDesc: 'Choose playlists containing your favorite songs to extract your music taste.',
  selectedTracksCount: (n) => <>{n} tracks selected</>,
  selectAll: 'Select All',
  deselectAll: 'Deselect All',
  playlistEmpty: 'Playlist is empty',
  loadingPlaylists: 'Loading your playlists...',
  submittedTitle: 'Submitted!',
  submittedDesc: (n) => `Your ${n} selected tracks are being analyzed. The DJ will see your music taste.`,
  canClosePage: 'You can close this page now.',
  selectedInPlaylist: (n) => `Selected ${n}`,
  loadingTracks: 'Loading tracks...',
  submitting: 'Analyzing...',
  pleaseSelectTracks: 'Please select tracks first',
  shareTracks: (n) => `Share ${n} tracks to DJ`,
};

const translations = {
  en: baseTranslations,
  zh: baseTranslations,
  ko: baseTranslations,
};

const LANG_LABELS = { en: 'EN', zh: 'ZH', ko: 'KO' };

const I18nContext = createContext();

export function I18nProvider({ children }) {
  const [lang, setLang] = useState(() => localStorage.getItem('crowdbeat_lang') || 'en');

  const switchLang = (newLang) => {
    setLang(newLang);
    localStorage.setItem('crowdbeat_lang', newLang);
  };

  const t = translations[lang] || translations.en;

  return (
    <I18nContext.Provider value={{ lang, switchLang, t, LANG_LABELS }}>
      {children}
    </I18nContext.Provider>
  );
}

export const useI18n = () => useContext(I18nContext);
