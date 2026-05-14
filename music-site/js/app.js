/* =============================================
   SMADS AFRICAN HITS – Main Application JS
   Developer: CHIMBINI STEVEN | Zambia-first
   Currency: ZMW (Zambian Kwacha)
   ============================================= */

// ── API Base ──────────────────────────────────────────────────────────────────
const API = {
    auth:    '/api/auth',
    tracks:  '/api/tracks',
    user:    '/api/user',
    admin:   '/api/admin',
    payment: '/api/payment',
    contact: '/api/contact',
};

// ── ZMW Currency ─────────────────────────────────────────────────────────────
function formatZMW(amount) {
    return 'K' + parseFloat(amount).toLocaleString('en-ZM', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// ── App State ─────────────────────────────────────────────────────────────────
const appState = {
    currentUser:  null,
    currentTrack: null,
    isPlaying:    false,
    volume:       75,
    queue:        [],
    queueIndex:   0,
    csrfToken:    '',
};

// ── Fetch CSRF Token ──────────────────────────────────────────────────────────
async function loadCsrfToken() {
    try {
        const data = await fetch('/api/csrf-token', { credentials: 'same-origin' });
        const json = await data.json();
        appState.csrfToken = json.csrf_token || '';
    } catch { /* non-critical — CSRF will be missing but server will reject */ }
}

// ── Fetch Wrapper ─────────────────────────────────────────────────────────────
async function apiFetch(url, options = {}) {
    // Automatically attach CSRF token to all state-changing requests
    const method = (options.method || 'GET').toUpperCase();
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
        options.headers = {
            'X-CSRFToken': appState.csrfToken,
            ...(options.headers || {}),
        };
    }

    let res;
    try {
        res = await fetch(url, {
            credentials: 'same-origin',
            headers: { 'Accept': 'application/json', ...(options.headers || {}) },
            ...options,
        });
    } catch (err) {
        console.error('Network error:', url, err.message);
        throw new Error('Network error – is the server running?');
    }

    // Read body as text first so we never crash on empty responses
    const text = await res.text();
    let data = {};
    if (text) {
        try {
            data = JSON.parse(text);
        } catch {
            console.error('JSON parse error for', url, '– body:', text.slice(0, 200));
            throw new Error('Server returned invalid response');
        }
    }

    // If CSRF token expired, refresh it and retry once
    if (res.status === 403 && data.error?.includes('CSRF')) {
        await loadCsrfToken();
        options.headers = { ...options.headers, 'X-CSRFToken': appState.csrfToken };
        return apiFetch(url, options);
    }

    if (!res.ok) {
        // Sanitize error messages — don't expose internal server details
        let errMsg = data.error || `Request failed (${res.status})`;
        // Strip any file paths, stack traces, or SQL from error messages
        if (res.status === 500) errMsg = 'Something went wrong on our end. Please try again.';
        throw new Error(errMsg);
    }
    return data;
}

// ── Utility ───────────────────────────────────────────────────────────────────
function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.className = `toast toast-${type} show`;
    toast.querySelector('.toast-msg').textContent = message;
    toast.querySelector('.toast-icon').textContent = type === 'success' ? '✓' : '✕';
    // Ensure screen readers announce the toast
    toast.setAttribute('aria-live', type === 'error' ? 'assertive' : 'polite');
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => toast.classList.remove('show'), 3500);
}

function formatDuration(seconds) {
    if (!seconds) return '0:00';
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
}

function formatNumber(n) {
    n = parseInt(n) || 0;
    if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M';
    if (n >= 1_000)     return (n / 1_000).toFixed(0) + 'K';
    return n.toString();
}

function timeAgo(dateStr) {
    const diff = (Date.now() - new Date(dateStr)) / 1000;
    if (diff < 60)    return 'just now';
    if (diff < 3600)  return Math.floor(diff / 60) + ' min ago';
    if (diff < 86400) return Math.floor(diff / 3600) + ' hr ago';
    return Math.floor(diff / 86400) + ' days ago';
}

function showLoading(container, msg = 'Loading...') {
    if (!container) return;
    // Show skeleton cards instead of plain text
    const isGrid = container.classList.contains('music-grid') ||
                   container.id === 'home-grid' ||
                   container.id === 'browse-grid';
    if (isGrid) {
        container.innerHTML = Array(8).fill(0).map(() => `
            <div class="skeleton-card" aria-hidden="true">
                <div class="skeleton-cover"></div>
                <div class="skeleton-body">
                    <div class="skeleton-line"></div>
                    <div class="skeleton-line short"></div>
                    <div class="skeleton-line xshort"></div>
                </div>
            </div>`).join('');
    } else {
        container.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:3rem;color:var(--text-secondary)">${msg}</div>`;
    }
}

function showEmpty(container, msg = 'No tracks found.') {
    if (!container) return;
    container.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:3rem;color:var(--text-secondary)">🎵 ${msg}</div>`;
}

function escHtml(str) {
    return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ── Auth State ────────────────────────────────────────────────────────────────
async function loadCurrentUser() {
    try {
        const data = await apiFetch(`${API.auth}/me`);
        appState.currentUser = data.user;
        updateNavForUser(data.user);
    } catch {
        appState.currentUser = null;
    }
}

// Apply maxlength to all auth modal inputs (runs once on page load)
function applyInputLimits() {
    const limits = {
        'input[name="username"]':     60,
        'input[name="display_name"]': 100,
        'input[name="email"]':        120,
        'input[name="password"]':     128,
        'input[name="login"]':        120,
        '#comment-input':             500,
        '#settings-display-name':     100,
        '#settings-bio':              1000,
        '#settings-website':          255,
        '#grant-amount':              12,
        '#grant-note':                255,
        '#cred-new-email':            120,
        '#cred-new-username':         60,
        '#cred-new-pass':             128,
        '#cred-current-pass':         128,
    };
    Object.entries(limits).forEach(([selector, max]) => {
        document.querySelectorAll(selector).forEach(el => {
            if (!el.getAttribute('maxlength')) el.setAttribute('maxlength', max);
        });
    });
}

function updateNavForUser(user) {
    const signInBtns  = document.querySelectorAll('.nav-signin');
    const profileBtns = document.querySelectorAll('.nav-profile');
    const logoutBtns  = document.querySelectorAll('#logout-btn, #logout-btn-mobile');
    if (user) {
        signInBtns.forEach(b => b.style.display = 'none');
        profileBtns.forEach(b => { b.style.display = ''; b.textContent = user.display_name; });
        logoutBtns.forEach(b => b.style.display = '');
        // Show email verification banner for unverified artists
        if (!user.email_verified && user.role === 'artist' && !user.is_admin) {
            showVerificationBanner(user);
        }
    } else {
        signInBtns.forEach(b => b.style.display = '');
        profileBtns.forEach(b => b.style.display = 'none');
        logoutBtns.forEach(b => b.style.display = 'none');
    }
}

function showVerificationBanner(user) {
    if (document.getElementById('verify-banner')) return; // already shown
    const banner = document.createElement('div');
    banner.id = 'verify-banner';
    banner.setAttribute('role', 'alert');
    banner.style.cssText = [
        'position:fixed', 'top:70px', 'left:0', 'right:0', 'z-index:800',
        'background:#ff6584', 'color:#fff', 'text-align:center',
        'padding:0.6rem 1rem', 'font-size:0.85rem', 'font-weight:600',
        'display:flex', 'align-items:center', 'justify-content:center', 'gap:1rem'
    ].join(';');
    // No dismiss button — verification is required to use artist features
    banner.innerHTML = `
        ⚠️ Please verify your email address to unlock music uploads.
        <button id="resend-verify-btn" style="background:rgba(255,255,255,0.25);border:1px solid rgba(255,255,255,0.5);color:#fff;padding:0.25rem 0.75rem;border-radius:50px;cursor:pointer;font-size:0.8rem">
            Resend Email
        </button>`;
    document.body.appendChild(banner);

    let resendCooldown = false;
    document.getElementById('resend-verify-btn')?.addEventListener('click', async function() {
        if (resendCooldown) { showToast('Please wait before resending.', 'error'); return; }
        this.disabled = true; this.textContent = 'Sending...';
        try {
            const data = await apiFetch('/api/auth/resend_verification', { method: 'POST' });
            showToast(data.message || 'Verification email sent!');
            this.textContent = 'Sent ✓';
            // 60-second cooldown to prevent spam
            resendCooldown = true;
            setTimeout(() => {
                resendCooldown = false;
                this.disabled = false;
                this.textContent = 'Resend Email';
            }, 60000);
        } catch (err) {
            showToast(err.message, 'error');
            this.disabled = false; this.textContent = 'Resend Email';
        }
    });
}

// ── Navbar ────────────────────────────────────────────────────────────────────
function initNavbar() {
    const navbar     = document.querySelector('.navbar');
    const hamburger  = document.querySelector('.hamburger');
    const mobileMenu = document.querySelector('.mobile-menu');

    window.addEventListener('scroll', () => {
        navbar?.classList.toggle('scrolled', window.scrollY > 50);
    });

    hamburger?.addEventListener('click', () => {
        mobileMenu?.classList.toggle('open');
        hamburger.classList.toggle('active');
        // Update aria-expanded for accessibility
        const isOpen = hamburger.classList.contains('active');
        hamburger.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
        const spans = hamburger.querySelectorAll('span');
        if (isOpen) {
            spans[0].style.transform = 'rotate(45deg) translate(5px, 5px)';
            spans[1].style.opacity = '0';
            spans[2].style.transform = 'rotate(-45deg) translate(5px, -5px)';
        } else {
            spans.forEach(s => { s.style.transform = ''; s.style.opacity = ''; });
        }
    });

    // Close mobile menu when any link inside it is clicked
    mobileMenu?.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', () => {
            mobileMenu.classList.remove('open');
            hamburger?.classList.remove('active');
            hamburger?.setAttribute('aria-expanded', 'false');
            hamburger?.querySelectorAll('span').forEach(s => {
                s.style.transform = ''; s.style.opacity = '';
            });
        });
    });

    // Close mobile menu when clicking outside
    document.addEventListener('click', (e) => {
        if (mobileMenu?.classList.contains('open') &&
            !mobileMenu.contains(e.target) &&
            !hamburger?.contains(e.target)) {
            mobileMenu.classList.remove('open');
            hamburger?.classList.remove('active');
            hamburger?.setAttribute('aria-expanded', 'false');
            hamburger?.querySelectorAll('span').forEach(s => {
                s.style.transform = ''; s.style.opacity = '';
            });
        }
    });
}

// ── Audio Engine ──────────────────────────────────────────────────────────────
const audio = new Audio();
audio.preload = 'metadata';

function updatePlayPauseIcon(playing) {
    document.querySelectorAll('.play-pause, .play-pause-large, #main-play').forEach(btn => {
        if (!btn) return;
        btn.innerHTML = playing
            ? '<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>'
            : '<svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><polygon points="5,3 19,12 5,21"/></svg>';
    });
}

function updateProgressBar(current, duration) {
    const pct = duration > 0 ? (current / duration) * 100 : 0;
    document.querySelectorAll('.progress-fill, #full-fill').forEach(el => {
        if (el) el.style.width = pct + '%';
    });
    document.querySelectorAll('.progress-time, #current-time').forEach((el, i) => {
        if (i % 2 === 0) el.textContent = formatDuration(Math.floor(current));
    });
}

// Audio event listeners
audio.addEventListener('timeupdate', () => {
    updateProgressBar(audio.currentTime, audio.duration || 0);
});
audio.addEventListener('ended', () => {
    appState.isPlaying = false;
    updatePlayPauseIcon(false);
    updateProgressBar(0, audio.duration || 0);
});
audio.addEventListener('error', () => {
    showToast('Could not play this track. The audio file may be missing.', 'error');
    appState.isPlaying = false;
    updatePlayPauseIcon(false);
});
audio.addEventListener('loadedmetadata', () => {
    // Update duration display
    document.querySelectorAll('.progress-time').forEach((el, i) => {
        if (i % 2 === 1) el.textContent = formatDuration(Math.floor(audio.duration));
    });
});

// ── Player Bar ────────────────────────────────────────────────────────────────
let isShuffled = false;
let isRepeating = false;

function initPlayerBar() {
    const bar = document.querySelector('.player-bar');
    if (!bar) return;
    const playPause     = bar.querySelector('.play-pause');
    const progressTrack = bar.querySelector('.progress-track');
    const volumeSlider  = bar.querySelector('.volume-slider');

    // Play / Pause toggle
    playPause?.addEventListener('click', () => {
        if (!appState.currentTrack) return;
        if (audio.paused) {
            audio.play().catch(() => showToast('Playback blocked. Tap play again.', 'error'));
            appState.isPlaying = true;
        } else {
            audio.pause();
            appState.isPlaying = false;
        }
        updatePlayPauseIcon(appState.isPlaying);
    });

    // Seek on progress bar click
    progressTrack?.addEventListener('click', (e) => {
        if (!audio.duration) return;
        const rect = progressTrack.getBoundingClientRect();
        const pct  = (e.clientX - rect.left) / rect.width;
        audio.currentTime = pct * audio.duration;
    });

    // Volume
    if (volumeSlider) {
        audio.volume = volumeSlider.value / 100;
        volumeSlider.addEventListener('input', (e) => {
            audio.volume = e.target.value / 100;
            appState.volume = e.target.value;
        });
    }

    // Shuffle button
    bar.querySelectorAll('.ctrl-btn').forEach(btn => {
        const title = btn.getAttribute('title') || '';
        if (title === 'Shuffle') {
            btn.addEventListener('click', () => {
                isShuffled = !isShuffled;
                btn.style.color = isShuffled ? 'var(--primary)' : '';
                showToast(isShuffled ? 'Shuffle on' : 'Shuffle off');
            });
        }
        if (title === 'Repeat') {
            btn.addEventListener('click', () => {
                isRepeating = !isRepeating;
                audio.loop = isRepeating;
                btn.style.color = isRepeating ? 'var(--primary)' : '';
                showToast(isRepeating ? 'Repeat on' : 'Repeat off');
            });
        }
        if (title === 'Previous') {
            btn.addEventListener('click', () => {
                if (audio.currentTime > 3) {
                    audio.currentTime = 0; // restart if past 3s
                } else {
                    playFromQueue(-1);
                }
            });
        }
        if (title === 'Next') {
            btn.addEventListener('click', () => playFromQueue(1));
        }
    });
}

function playFromQueue(direction) {
    if (!appState.queue?.length) return;
    let idx = appState.queueIndex + direction;
    if (isShuffled) idx = Math.floor(Math.random() * appState.queue.length);
    if (idx < 0) idx = appState.queue.length - 1;
    if (idx >= appState.queue.length) idx = 0;
    appState.queueIndex = idx;
    playTrack(appState.queue[idx]);
}

// ── Play Track ────────────────────────────────────────────────────────────────
async function playTrack(track) {
    const bar = document.querySelector('.player-bar');
    if (!bar) return;

    // Update UI
    bar.classList.add('active');
    appState.currentTrack = track;

    const cover  = bar.querySelector('.player-cover');
    const title  = bar.querySelector('.player-title');
    const artist = bar.querySelector('.player-artist');
    if (cover)  cover.src = track.cover_url || 'data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'48\' height=\'48\' viewBox=\'0 0 48 48\'%3E%3Crect width=\'48\' height=\'48\' rx=\'8\' fill=\'%231a1a2e\'/%3E%3Cpath d=\'M16 32V16l20 8-20 8z\' fill=\'%236c63ff\' opacity=\'0.7\'/%3E%3C/svg%3E';
    if (title)  title.textContent  = track.title;
    if (artist) artist.textContent = track.artist_name;

    // Set audio source — use the direct file URL
    const audioSrc = track.audio_url;
    if (!audioSrc) {
        showToast('No audio file for this track.', 'error');
        return;
    }

    // If same track, just toggle play/pause
    if (audio.src && audio.src.endsWith(audioSrc) && !audio.ended) {
        if (audio.paused) {
            audio.play().catch(() => {});
            appState.isPlaying = true;
        } else {
            audio.pause();
            appState.isPlaying = false;
        }
        updatePlayPauseIcon(appState.isPlaying);
        return;
    }

    // New track — load and play
    audio.pause();
    audio.src = audioSrc;
    audio.load();
    audio.volume = (appState.volume || 75) / 100;

    try {
        await audio.play();
        appState.isPlaying = true;
        updatePlayPauseIcon(true);
        showToast(`▶ ${track.title}`);
    } catch (err) {
        // Autoplay blocked — show play button, user must tap
        appState.isPlaying = false;
        updatePlayPauseIcon(false);
        showToast(`Tap ▶ to play: ${track.title}`);
    }

    // Record play count
    try {
        await fetch(`${API.tracks}/play/${track.id}`, { method: 'POST', credentials: 'same-origin' });
    } catch { /* non-critical */ }
}

// ── Share Track ───────────────────────────────────────────────────────────────
async function shareTrack(track) {
    const url = `${location.origin}/player.html?id=${track.id}`;
    try {
        if (navigator.share) {
            await navigator.share({ title: track.title, text: `Listen to ${track.title} by ${track.artist_name}`, url });
        } else {
            await navigator.clipboard.writeText(url);
            showToast('Link copied to clipboard!');
        }
        await fetch(`${API.tracks}/share/${track.id}`, { method: 'POST', credentials: 'same-origin' });
    } catch { /* user cancelled */ }
}

function createMusicCard(track) {
    const card = document.createElement('div');
    card.className = 'music-card';
    const coverSrc = track.cover_url || 'data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'300\' height=\'300\' viewBox=\'0 0 300 300\'%3E%3Crect width=\'300\' height=\'300\' fill=\'%231a1a2e\'/%3E%3Ccircle cx=\'150\' cy=\'150\' r=\'60\' fill=\'none\' stroke=\'%236c63ff\' stroke-width=\'2\' opacity=\'0.4\'/%3E%3Cpath d=\'M125 170V130l50 20-50 20z\' fill=\'%236c63ff\' opacity=\'0.7\'/%3E%3C/svg%3E';

    card.innerHTML = `
        <div class="music-card-cover">
            <img src="${coverSrc}" alt="${escHtml(track.title)}" loading="lazy">
            <div class="play-overlay">
                <button class="play-btn-large" aria-label="Play ${escHtml(track.title)}">
                    <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor"><polygon points="5,3 19,12 5,21"/></svg>
                </button>
            </div>
        </div>
        <div class="music-card-body">
            <div class="music-card-title">${escHtml(track.title)}</div>
            <div class="music-card-artist">${escHtml(track.artist_name)}</div>
            <div class="music-card-meta">
                <span class="music-card-genre">${escHtml(track.genre)}</span>
                <div class="music-card-actions">
                    <button class="action-btn like-btn${track.user_liked ? ' liked' : ''}" title="Like" aria-label="Like" data-id="${track.id}">♥</button>
                    <button class="action-btn share-btn" title="Share" aria-label="Share">⤴</button>
                    ${track.is_free_dl ? `<a class="action-btn" href="${API.tracks}/download/${track.id}" title="Download" aria-label="Download" download>↓</a>` : ''}
                </div>
            </div>
        </div>`;

    card.querySelector('.play-btn-large').addEventListener('click', (e) => {
        e.stopPropagation();
        playTrack(track);
    });

    card.querySelector('.like-btn')?.addEventListener('click', async (e) => {
        e.stopPropagation();
        if (!appState.currentUser) { showToast('Sign in to like tracks', 'error'); return; }
        try {
            const res = await apiFetch(`${API.tracks}/like/${track.id}`, { method: 'POST' });
            e.currentTarget.classList.toggle('liked', res.liked);
            showToast(res.liked ? 'Added to favorites' : 'Removed from favorites');
        } catch (err) { showToast(err.message, 'error'); }
    });

    card.querySelector('.share-btn')?.addEventListener('click', (e) => {
        e.stopPropagation();
        shareTrack(track);
    });

    card.addEventListener('click', () => playTrack(track));
    return card;
}

// ── Track Row Component ───────────────────────────────────────────────────────
function createTrackRow(track, index) {
    const row = document.createElement('div');
    row.className = 'track-row';
    const coverSrc = track.cover_url || 'data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'44\' height=\'44\' viewBox=\'0 0 44 44\'%3E%3Crect width=\'44\' height=\'44\' rx=\'8\' fill=\'%231a1a2e\'/%3E%3Cpath d=\'M14 30V14l18 8-18 8z\' fill=\'%236c63ff\' opacity=\'0.7\'/%3E%3C/svg%3E';

    row.innerHTML = `
        <span class="track-num">${index + 1}</span>
        <span class="track-play-mini">▶</span>
        <img class="track-cover" src="${coverSrc}" alt="${escHtml(track.title)}" loading="lazy">
        <div class="track-info">
            <div class="track-title">${escHtml(track.title)}</div>
            <div class="track-artist">${escHtml(track.artist_name)}</div>
        </div>
        <span class="track-genre">${escHtml(track.genre)}</span>
        <span class="track-duration">${formatDuration(track.duration)}</span>
        <div class="track-actions">
            <button class="action-btn like-btn" title="Like" data-id="${track.id}">♥</button>
            ${track.is_free_dl ? `<a class="action-btn" href="${API.tracks}/download/${track.id}" title="Download" download>↓</a>` : ''}
        </div>`;

    row.addEventListener('click', () => playTrack(track));
    row.querySelector('.like-btn')?.addEventListener('click', async (e) => {
        e.stopPropagation();
        if (!appState.currentUser) { showToast('Sign in to like tracks', 'error'); return; }
        try {
            const res = await apiFetch(`${API.tracks}/like/${track.id}`, { method: 'POST' });
            e.currentTarget.classList.toggle('liked', res.liked);
        } catch (err) { showToast(err.message, 'error'); }
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
    // Track the element that opened each modal so we can restore focus on close
    const openerMap = new WeakMap();

    function openModal(overlay) {
        if (!overlay) return;
        overlay.classList.add('open');
        overlay.setAttribute('aria-modal', 'true');
        overlay.setAttribute('role', 'dialog');
        // Store opener
        openerMap.set(overlay, document.activeElement);
        // Focus first focusable element inside modal
        const focusable = overlay.querySelectorAll(
            'button, input, select, textarea, a[href], [tabindex]:not([tabindex="-1"])'
        );
        if (focusable.length) setTimeout(() => focusable[0].focus(), 50);
        // Trap focus
        overlay._trapFocus = (e) => {
            if (e.key === 'Escape') { closeModal(overlay); return; }
            if (e.key !== 'Tab') return;
            const items = [...overlay.querySelectorAll(
                'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'
            )];
            if (!items.length) return;
            const first = items[0];
            const last  = items[items.length - 1];
            if (e.shiftKey && document.activeElement === first) {
                e.preventDefault(); last.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
                e.preventDefault(); first.focus();
            }
        };
        document.addEventListener('keydown', overlay._trapFocus);
    }

    function closeModal(overlay) {
        if (!overlay) return;
        overlay.classList.remove('open');
        document.removeEventListener('keydown', overlay._trapFocus);
        // Restore focus to opener
        const opener = openerMap.get(overlay);
        if (opener && opener.focus) opener.focus();
    }

    document.querySelectorAll('[data-modal]').forEach(trigger => {
        trigger.addEventListener('click', (e) => {
            e.preventDefault();
            const modal = document.getElementById(trigger.dataset.modal);
            openModal(modal);
        });
    });

    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closeModal(overlay);
        });
        overlay.querySelector('.modal-close')?.addEventListener('click', () => closeModal(overlay));
    });
}

// ── Genre Filter ──────────────────────────────────────────────────────────────
function initGenreFilter(gridId) {
    document.querySelectorAll('.genre-pill').forEach(pill => {
        pill.addEventListener('click', async () => {
            document.querySelectorAll('.genre-pill').forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
            const genre = pill.dataset.genre;
            const grid  = document.getElementById(gridId);
            if (!grid) return;
            showLoading(grid);
            try {
                const url = genre === 'all'
                    ? `${API.tracks}/list?limit=20`
                    : `${API.tracks}/list?genre=${encodeURIComponent(genre)}&limit=20`;
                const data = await apiFetch(url);
                grid.innerHTML = '';
                if (!data.tracks?.length) { showEmpty(grid); return; }
                data.tracks.forEach(t => grid.appendChild(createMusicCard(t)));
            } catch { showEmpty(grid, 'Failed to load tracks.'); }
        });
    });
}

// ── Search ────────────────────────────────────────────────────────────────────
function initSearch() {
    const input = document.querySelector('.search-input');
    if (!input) return;
    input.addEventListener('input', debounce(async (e) => {
        const q    = e.target.value.trim();
        const grid = document.querySelector('.browse-grid');
        if (!grid) return;
        if (q.length < 2) { loadBrowseGrid(grid); return; }
        showLoading(grid);
        try {
            const data = await apiFetch(`${API.tracks}/search?q=${encodeURIComponent(q)}`);
            grid.innerHTML = '';
            const count = document.getElementById('results-count');
            if (!data.tracks?.length) {
                showEmpty(grid, `No results for "${q}"`);
                if (count) count.textContent = '0 results';
                return;
            }
            data.tracks.forEach(t => grid.appendChild(createMusicCard(t)));
            if (count) count.textContent = `${data.tracks.length} results for "${q}"`;
        } catch { showEmpty(grid, 'Search failed. Try again.'); }
    }, 350));
}

async function loadBrowseGrid(grid) {
    if (!grid) return;
    showLoading(grid);
    try {
        const data = await apiFetch(`${API.tracks}/list?limit=20`);
        grid.innerHTML = '';
        if (!data.tracks?.length) { showEmpty(grid, 'No tracks uploaded yet. Be the first!'); return; }
        data.tracks.forEach(t => grid.appendChild(createMusicCard(t)));
        const count = document.getElementById('results-count');
        if (count) count.textContent = `Showing ${data.tracks.length} of ${data.total} tracks`;
    } catch { showEmpty(grid, 'Failed to load tracks. Check your connection.'); }
}

// ── Upload Form ───────────────────────────────────────────────────────────────
function initUploadForm() {
    const form = document.getElementById('upload-form');
    if (!form) return;

    ['audio-dropzone', 'cover-dropzone'].forEach(id => {
        const zone  = document.getElementById(id);
        const input = zone?.querySelector('input[type="file"]');
        if (!zone || !input) return;
        zone.addEventListener('click', () => input.click());
        zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
        zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
        zone.addEventListener('drop', e => {
            e.preventDefault(); zone.classList.remove('dragover');
            const file = e.dataTransfer.files[0];
            if (file) { input.files = e.dataTransfer.files; handleFilePreview(id, file); }
        });
        input.addEventListener('change', () => { if (input.files[0]) handleFilePreview(id, input.files[0]); });
    });
}

function handleFilePreview(zoneId, file) {
    const zone = document.getElementById(zoneId);
    if (!zone) return;
    const p = zone.querySelector('p');
    if (p) p.innerHTML = `<strong>${escHtml(file.name)}</strong> (${(file.size / 1024 / 1024).toFixed(1)}MB)`;
    if (zoneId === 'cover-dropzone' && file.type.startsWith('image/')) {
        const preview = document.getElementById('cover-preview');
        if (preview) { preview.src = URL.createObjectURL(file); preview.style.display = 'block'; }
    }
}

// ── Contact Form ──────────────────────────────────────────────────────────────
function initContactForm() {
    const form = document.getElementById('contact-form');
    if (!form) return;
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = form.querySelector('[type="submit"]');
        if (btn) { btn.disabled = true; btn.textContent = 'Sending...'; }
        // Map form field IDs to backend-expected keys
        const body = {
            name:    document.getElementById('contact-name')?.value    || '',
            email:   document.getElementById('contact-email')?.value   || '',
            subject: document.getElementById('contact-subject')?.value || '',
            message: document.getElementById('contact-message')?.value || '',
        };
        try {
            const data = await apiFetch(`${API.contact}/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            showToast(data.message || 'Message sent!');
            form.reset();
        } catch (err) {
            showToast(err.message || 'Failed to send message.', 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Send Message'; }
        }
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

// ── Auth Modal ────────────────────────────────────────────────────────────────
function initAuthModal() {
    const loginForm    = document.getElementById('login-form');
    const registerForm = document.getElementById('register-form');

    loginForm?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = loginForm.querySelector('[type="submit"]');
        if (btn) { btn.disabled = true; btn.textContent = 'Signing in...'; }
        const fd = new FormData(loginForm);
        try {
            const data = await apiFetch(`${API.auth}/login`, { method: 'POST', body: fd });
            appState.currentUser = data.user;
            updateNavForUser(data.user);
            document.getElementById('auth-modal')?.classList.remove('open');
            showToast(`Welcome back, ${data.user.display_name}!`);
            // Artists go to their profile; everyone else reloads current page
            if (data.user.role === 'artist' && !data.user.is_admin) {
                setTimeout(() => location.replace('profile.html'), 800);
            } else {
                setTimeout(() => location.reload(), 800);
            }
        } catch (err) {
            showToast(err.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Sign In'; }
        }
    });
    registerForm?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = registerForm.querySelector('[type="submit"]');
        if (btn) { btn.disabled = true; btn.textContent = 'Creating account...'; }
        const fd = new FormData(registerForm);
        try {
            const data = await apiFetch(`${API.auth}/register`, { method: 'POST', body: fd });
            appState.currentUser = data.user;
            updateNavForUser(data.user);
            document.getElementById('auth-modal')?.classList.remove('open');
            showToast(`Welcome to SMADS African Hits, ${data.user.display_name}! Check your email to verify your account.`);
            // Redirect to profile so the new user sees their own fresh data
            setTimeout(() => location.replace('profile.html'), 1200);
        } catch (err) {
            showToast(err.message, 'error');
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = 'Create Account'; }
        }
    });

    document.getElementById('logout-btn')?.addEventListener('click', doLogout);
    document.getElementById('logout-btn-mobile')?.addEventListener('click', doLogout);
}

// ── Logout (global so profile.html and other pages can call it directly) ──────
async function doLogout() {
    try {
        await apiFetch(`${API.auth}/logout`, { method: 'POST' });
    } catch { /* ignore — session is cleared server-side regardless */ }
    appState.currentUser = null;
    updateNavForUser(null);
    showToast('Logged out.');
    setTimeout(() => location.replace('/'), 800);
}

// ── Scroll Animations ─────────────────────────────────────────────────────────
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

// ── Debounce ──────────────────────────────────────────────────────────────────
function debounce(fn, delay) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), delay); };
}

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    // Load CSRF token but never block UI init if the server is unreachable
    loadCsrfToken().catch(() => {});

    applyInputLimits();      // enforce maxlength on all inputs
    initNavbar();
    initPlayerBar();
    initTabs();
    initModals();
    initFAQ();
    initSearch();
    initUploadForm();
    initContactForm();
    initAuthModal();
    await loadCurrentUser();
    setTimeout(initScrollAnimations, 200);
});
