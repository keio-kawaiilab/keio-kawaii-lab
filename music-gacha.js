'use strict';
/* MV-only gacha: each distinct song is equally likely; opens the chosen YouTube MV in a new tab. */
(() => {
  const get = id => document.getElementById(id);
  const drawButton = get('draw-button');
  const rerollButton = get('reroll-button');
  const errorEl = get('load-error');
  const resultSection = get('result-section');
  const groupEl = get('result-group');
  const titleEl = get('result-title');
  const linkEl = get('result-link');
  const imageEl = get('result-thumb');
  const placeholderEl = get('thumbnail-placeholder');
  const resultEl = get('result');
  let songs = [];

  const videoUrl = id => `https://www.youtube.com/watch?v=${encodeURIComponent(id)}`;
  const valid = item => item && typeof item.title === 'string' && !!item.title.trim() &&
    typeof item.group === 'string' && !!item.group.trim() &&
    typeof item.youtubeId === 'string' && /^[\w-]{11}$/.test(item.youtubeId) &&
    item.videoType === 'MV';

  function randomIndex(n) {
    if (window.crypto && window.crypto.getRandomValues) {
      const max = 0x100000000;
      const limit = Math.floor(max / n) * n;
      const arr = new Uint32Array(1);
      do { window.crypto.getRandomValues(arr); } while (arr[0] >= limit);
      return arr[0] % n;
    }
    return Math.floor(Math.random() * n);
  }

  function pickSong() {
    // Every song has exactly the same chance at every draw.
    return songs[randomIndex(songs.length)];
  }

  function showSong(song) {
    const url = videoUrl(song.youtubeId);
    groupEl.textContent = song.group;
    titleEl.textContent = song.title;
    linkEl.href = url;
    linkEl.hidden = false;
    resultSection.hidden = false;
    resultEl.dataset.state = 'drawn';
    imageEl.alt = `${song.group}「${song.title}」のYouTubeサムネイル`;
    imageEl.hidden = false;
    placeholderEl.hidden = true;
    imageEl.onerror = () => { imageEl.hidden = true; placeholderEl.hidden = false; };
    imageEl.src = `https://i.ytimg.com/vi/${encodeURIComponent(song.youtubeId)}/hqdefault.jpg`;
    rerollButton.hidden = false;
    return url;
  }

  function draw() {
    if (!songs.length) return;
    const chosen = pickSong();
    const url = showSong(chosen);
    // Must remain in the actual click handler to avoid browser popup blockers.
    window.open(url, '_blank', 'noopener,noreferrer');
  }

  function normalize(data) {
    if (!data || !Array.isArray(data.songs)) throw Error('Invalid song data');
    const map = new Map();
    const names = new Set();
    for (const song of data.songs) {
      if (!valid(song)) continue;
      const key = `${song.group.trim()}::${song.title.trim().normalize('NFKC').toLowerCase()}`;
      if (map.has(song.youtubeId) || names.has(key)) continue;
      map.set(song.youtubeId, song);
      names.add(key);
    }
    return [...map.values()];
  }

  async function loadSongs() {
    try {
      let data;
      const embedded = get('embedded-song-data');
      // Standalone preview is usable even when opened as file://.
      if (location.protocol === 'file:' && embedded) {
        data = JSON.parse(embedded.textContent);
      } else {
        try {
          // GitHub Actions commits with GITHUB_TOKEN do not trigger a Pages build.
          // Read the canonical main-branch JSON directly; use the Pages copy
          // if GitHub's raw endpoint is temporarily unavailable.
          const candidates = [
            'https://raw.githubusercontent.com/keio-kawaiilab/keio-kawaii-lab/main/data/music-gacha.json',
            './data/music-gacha.json',
          ];
          let lastError;
          for (const source of candidates) {
            try {
              const response = await fetch(source, { cache: 'no-store' });
              if (!response.ok) throw Error(`HTTP ${response.status}`);
              const candidate = await response.json();
              if (!Array.isArray(candidate.songs) || !candidate.songs.length) {
                throw Error('Invalid catalog');
              }
              data = candidate;
              break;
            } catch (error) {
              lastError = error;
            }
          }
          if (!data) throw lastError || Error('Catalog unavailable');
        } catch (error) {
          if (!embedded) throw error;
          data = JSON.parse(embedded.textContent);
        }
      }
      songs = normalize(data);
      if (!songs.length) throw Error('No valid songs');
      drawButton.disabled = false;
    } catch (error) {
      console.error('[Music Gacha] Cannot load data:', error);
      errorEl.textContent = '曲を読み込めませんでした。ページを再読み込みしてください。';
      errorEl.hidden = false;
    }
  }

  drawButton.addEventListener('click', draw);
  rerollButton.addEventListener('click', draw);
  loadSongs();
})();
