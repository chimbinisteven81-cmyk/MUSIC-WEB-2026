/* =============================================
   SOUNDWAVE - Main Application JS
   TODO: Replace mock data with API calls to backend
   ============================================= */

// ── Mock Data (replace with API responses) ──────────────────────────────────
const MOCK_TRACKS = [
  { id: 1, title: "Neon Dreams", artist: "Luna Waves", genre: "Electronic", duration: "3:42", cover: "https://picsum.photos/seed/t1/300/300", plays: "1.2M", liked: false },
  { id: 2, title: "Midnight Soul", artist: "The Velvet", genre: "R&B", duration: "4:15", cover: "https://picsum.photos/seed/t2/300/300", plays: "890K", liked: true },
  { id: 3, title: "Golden Hour", artist: "Solaris", genre: "Pop", duration: "3:28", cover: "https://picsum.photos/seed/t3/300/300", plays: "2.1M", liked: false },
  { id: 4, title: "Deep Space", artist: "Orbit X", genre: "Electronic", duration: "5:01", cover: "https://picsum.photos/seed/t4/300/300", plays: "456K", liked: false },
  { id: 5, title: "City Lights", artist: "Nova Beat", genre: "Hip-Hop", duration: "3:55", cover: "https://picsum.photos/seed/t5/300/300", plays: "3.4M", liked: true },
  { id: 6, title: "Rainy Season", artist: "Chill Mode", genre: "Lo-Fi", duration: "4:33", cover: "https://picsum.photos/seed/t6/300/300", plays: "780K", liked: false },
  { id: 7, title: "Fire & Ice", artist: "Blaze", genre: "Rock", duration: "3:18", cover: "https://picsum.photos/seed/t7/300/300", plays: "1.5M", liked: false },
  { id: 8, title: "Sunset Drive", artist: "Retro Vibes", genre: "Synthwave", duration: "4:47", cover: "https://picsum.photos/seed/t8/300/300", plays: "920K", liked: true },
];

const MOCK_ARTISTS = [
  { id: 1, name: "Luna Waves", genre: "Electronic", followers: "124K", avatar: "https://picsum.photos/seed/a1/200/200" },
  { id: 2, name: "The Velvet", genre: "R&B / Soul", followers: "89K", avatar: "https://picsum.photos/seed/a2/200/200" },
  { id: 3, name: "Solaris", genre: "Pop", followers: "312K", avatar: "https://picsum.photos/seed/a3/200/200" },
  { id: 4, name: "Nova Beat", genre: "Hip-Hop", followers: "567K", avatar: "https://picsum.photos/seed/a4/200/200" },
];

// ── Player State ─────────────────────────────────────────────────────────────
const playerState = {
  currentTrack: null,
  isPlaying: false,
  progress: 35,
  volume: 75,
};

// ── Utility Functions ─────────────────────────────────────────────────────────
function showToast(message, type = 'success') {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.className = `toast toast-${type} show`;
  toast.querySelector('.toast-msg').textContent = message;
  toast.querySelector('.toast-icon').textContent = type === 'success' ? '✓' : '✕';
  setTimeout(() => toast.classList.remove('show'), 3000);
}

function formatNumber(n) {
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(0) + 'K';
  return n;
}

// ── Navbar ────────────────────────────────────────────────────────────────────
function initNavbar() {
  const navbar = document.querySelector('.navbar');
  const hamburger = document.querySelector('.hamburger');
  const mobileMenu = document.querySelector('.mobile-menu');

  window.addEventListener('scroll', () => {
    navbar?.classList.toggle('scrolled', window.scrollY > 50);
  });

  hamburger?.addEventListener('click', () => {
    mobileMenu?.classList.toggle('open');
    const spans = hamburger.querySelectorAll('span');
    hamburger.classList.toggle('active');
    if (hamburger.classList.contains('active')) {
      spans[0].style.transform = 'rotate(45deg) translate(5px, 5px)';
      spans[1].style.opacity = '0';
      spans[2].style.transform = 'rotate(-45deg) translate(5px, -5px)';
    } else {
      spans.forEach(s => { s.style.transform = ''; s.style.opacity = ''; });
    }
  });

  // Set active nav link
  const currentPage = window.location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nav-links a, .mobile-menu a').forEach(link => {
    if (link.getAttribute('href') === currentPage) link.classList.add('active');
  });
}

// ── Player Bar ────────────────────────────────────────────────────────────────
function initPlayerBar() {
  const bar = document.querySelector('.player-bar');
  if (!bar) return;

  const playPause = bar.querySelector('.play-pause');
  const progressTrack = bar.querySelector('.progress-track');
  const progressFill = bar.querySelector('.progress-fill');
  const volumeSlider = bar.querySelector('.volume-slider');

  playPause?.addEventListener('click', () => {
    playerState.isPlaying = !playerState.isPlaying;
    playPause.innerHTML = playerState.isPlaying
      ? '<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>'
      : '<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><polygon points="5,3 19,12 5,21"/></svg>';
  });

  progressTrack?.addEventListener('click', (e) => {
    const rect = progressTrack.getBoundingClientRect();
    const pct = ((e.clientX - rect.left) / rect.width) * 100;
    if (progressFill) progressFill.style.width = pct + '%';
  });

  volumeSlider?.addEventListener('input', (e) => {
    playerState.volume = e.target.value;
  });
}

// ── Play Track ────────────────────────────────────────────────────────────────
function playTrack(track) {
  const bar = document.querySelector('.player-bar');
  if (!bar) return;
  bar.classList.add('active');
  playerState.currentTrack = track;
  playerState.isPlaying = true;

  const cover = bar.querySelector('.player-cover');
  const title = bar.querySelector('.player-title');
  const artist = bar.querySelector('.player-artist');
  if (cover) cover.src = track.cover;
  if (title) title.textContent = track.title;
  if (artist) artist.textContent = track.artist;

  const playPause = bar.querySelector('.play-pause');
  if (playPause) playPause.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>';

  showToast(`Now playing: ${track.title}`);
}

// ── Music Card Component ──────────────────────────────────────────────────────
function createMusicCard(track) {
  const card = document.createElement('div');
  card.className = 'music-card';
  card.innerHTML = `
    <div class="music-card-cover">
      <img src="${track.cover}" alt="${track.title}" loading="lazy">
      <div class="play-overlay">
        <button class="play-btn-large" aria-label="Play ${track.title}">
          <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor"><polygon points="5,3 19,12 5,21"/></svg>
        </button>
      </div>
      ${track.badge ? `<span class="music-card-badge">${track.badge}</span>` : ''}
    </div>
    <div class="music-card-body">
      <div class="music-card-title">${track.title}</div>
      <div class="music-card-artist">${track.artist}</div>
      <div class="music-card-meta">
        <span class="music-card-genre">${track.genre}</span>
        <div class="music-card-actions">
          <button class="action-btn like-btn ${track.liked ? 'liked' : ''}" title="Like" aria-label="Like">♥</button>
          <button class="action-btn" title="Download" aria-label="Download">↓</button>
        </div>
      </div>
    </div>`;

  card.querySelector('.play-btn-large').addEventListener('click', (e) => {
    e.stopPropagation();
    playTrack(track);
  });
  card.querySelector('.like-btn').addEventListener('click', (e) => {
    e.stopPropagation();
    track.liked = !track.liked;
    e.currentTarget.classList.toggle('liked', track.liked);
    showToast(track.liked ? 'Added to favorites' : 'Removed from favorites');
  });
  card.querySelector('[title="Download"]').addEventListener('click', (e) => {
    e.stopPropagation();
    // TODO: Connect to backend download endpoint
    showToast('Download started');
  });
  card.addEventListener('click', () => playTrack(track));
  return card;
}

// ── Track Row Component ───────────────────────────────────────────────────────
function createTrackRow(track, index) {
  const row = document.createElement('div');
  row.className = 'track-row';
  row.innerHTML = `
    <span class="track-num">${index + 1}</span>
    <span class="track-play-mini">▶</span>
    <img class="track-cover" src="${track.cover}" alt="${track.title}" loading="lazy">
    <div class="track-info">
      <div class="track-title">${track.title}</div>
      <div class="track-artist">${track.artist}</div>
    </div>
    <span class="track-genre">${track.genre}</span>
    <span class="track-duration">${track.duration}</span>
    <div class="track-actions">
      <button class="action-btn like-btn ${track.liked ? 'liked' : ''}" title="Like">♥</button>
      <button class="action-btn" title="Download">↓</button>
    </div>`;

  row.addEventListener('click', () => playTrack(track));
  row.querySelector('.like-btn').addEventListener('click', (e) => {
    e.stopPropagation();
    track.liked = !track.liked;
    e.currentTarget.classList.toggle('liked', track.liked);
    showToast(track.liked ? 'Added to favorites' : 'Removed from favorites');
  });
  return row;
}

// ── Tabs ──────────────────────────────────────────────────────────────────────
function initTabs() {
  document.querySelectorAll('.tabs').forEach(tabGroup => {
    tabGroup.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const target = btn.dataset.tab;
        tabGroup.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const container = tabGroup.closest('.tabs-wrapper') || document;
        container.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        const targetEl = container.querySelector(`#tab-${target}`);
        if (targetEl) targetEl.classList.add('active');
      });
    });
  });
}

// ── Modals ────────────────────────────────────────────────────────────────────
function initModals() {
  document.querySelectorAll('[data-modal]').forEach(trigger => {
    trigger.addEventListener('click', () => {
      const modal = document.getElementById(trigger.dataset.modal);
      modal?.classList.add('open');
    });
  });
  document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) overlay.classList.remove('open');
    });
    overlay.querySelector('.modal-close')?.addEventListener('click', () => overlay.classList.remove('open'));
  });
}

// ── Genre Filter ──────────────────────────────────────────────────────────────
function initGenreFilter() {
  document.querySelectorAll('.genre-pill').forEach(pill => {
    pill.addEventListener('click', () => {
      document.querySelectorAll('.genre-pill').forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      const genre = pill.dataset.genre;
      // TODO: Connect to backend filter API
      filterTracks(genre);
    });
  });
}

function filterTracks(genre) {
  const filtered = genre === 'all' ? MOCK_TRACKS : MOCK_TRACKS.filter(t => t.genre.toLowerCase() === genre.toLowerCase());
  const grid = document.querySelector('.browse-grid');
  if (!grid) return;
  grid.innerHTML = '';
  filtered.forEach(t => grid.appendChild(createMusicCard(t)));
  if (filtered.length === 0) {
    grid.innerHTML = '<p class="text-muted text-center" style="grid-column:1/-1;padding:3rem">No tracks found for this genre.</p>';
  }
}

// ── Search ────────────────────────────────────────────────────────────────────
function initSearch() {
  const input = document.querySelector('.search-input');
  if (!input) return;
  input.addEventListener('input', debounce((e) => {
    const q = e.target.value.toLowerCase();
    // TODO: Replace with backend search API call
    const results = MOCK_TRACKS.filter(t =>
      t.title.toLowerCase().includes(q) || t.artist.toLowerCase().includes(q) || t.genre.toLowerCase().includes(q)
    );
    const grid = document.querySelector('.browse-grid');
    if (!grid) return;
    grid.innerHTML = '';
    results.forEach(t => grid.appendChild(createMusicCard(t)));
  }, 300));
}

function debounce(fn, delay) {
  let timer;
  return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), delay); };
}

// ── Upload Form ───────────────────────────────────────────────────────────────
function initUploadForm() {
  const form = document.getElementById('upload-form');
  if (!form) return;

  const dropzone = form.querySelector('.upload-zone');
  dropzone?.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('dragover'); });
  dropzone?.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
  dropzone?.addEventListener('drop', (e) => {
    e.preventDefault(); dropzone.classList.remove('dragover');
    const file = e.dataTransfer.files[0];
    if (file) dropzone.querySelector('p').innerHTML = `<strong>${file.name}</strong> ready to upload`;
  });

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    // TODO: POST form data to backend upload API with payment verification
    showToast('Track submitted for review!');
    form.reset();
  });
}

// ── Contact Form ──────────────────────────────────────────────────────────────
function initContactForm() {
  const form = document.getElementById('contact-form');
  form?.addEventListener('submit', (e) => {
    e.preventDefault();
    // TODO: POST to backend contact/email API
    showToast('Message sent! We\'ll get back to you soon.');
    form.reset();
  });
}

// ── FAQ Accordion ─────────────────────────────────────────────────────────────
function initFAQ() {
  document.querySelectorAll('.faq-item').forEach(item => {
    item.querySelector('.faq-question')?.addEventListener('click', () => {
      const isOpen = item.classList.contains('open');
      document.querySelectorAll('.faq-item').forEach(i => i.classList.remove('open'));
      if (!isOpen) item.classList.add('open');
    });
  });
}

// ── Animate on Scroll ─────────────────────────────────────────────────────────
function initScrollAnimations() {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.style.animation = 'fadeInUp 0.6s ease forwards';
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1 });

  document.querySelectorAll('.music-card, .stat-card, .card, .track-row').forEach(el => {
    el.style.opacity = '0';
    observer.observe(el);
  });
}

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initNavbar();
  initPlayerBar();
  initTabs();
  initModals();
  initGenreFilter();
  initSearch();
  initUploadForm();
  initContactForm();
  initFAQ();
  setTimeout(initScrollAnimations, 100);
});
