# -*- coding: utf-8 -*-
"""
SMADS African Hits – Flask Backend
Developer: CHIMBINI STEVEN
Region: Africa (Zambia-first)
Currency: Zambian Kwacha (ZMW)
Database: MySQL (XAMPP / phpMyAdmin)
"""
import os, secrets, time, threading, smtplib
from mutagen import File as MutagenFile
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from collections import defaultdict
from datetime import timedelta
from functools import wraps
from flask import Flask, request, jsonify, session, send_from_directory, abort
from flask_wtf.csrf import CSRFProtect, generate_csrf, validate_csrf
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import pymysql
import pymysql.cursors

# Fix 10: Load .env file in development if python-dotenv is available
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'api', '.env')
    if os.path.exists(_env_path):
        load_dotenv(_env_path)
        print(f'[SMADS] Loaded environment from {_env_path}')
except ImportError:
    pass  # python-dotenv not installed — env vars must be set manually


# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
UPLOAD_AUDIO  = os.path.join(BASE_DIR, 'uploads', 'audio')
UPLOAD_COVER  = os.path.join(BASE_DIR, 'uploads', 'covers')
UPLOAD_AVATAR = os.path.join(BASE_DIR, 'uploads', 'avatars')
ALLOWED_AUDIO = {'mp3', 'wav', 'flac', 'aac', 'ogg', 'm4a'}
ALLOWED_IMG   = {'jpg', 'jpeg', 'png', 'webp', 'gif'}
MAX_AUDIO_MB  = 200
MAX_IMG_MB    = 10

# ZMW pricing (Zambian Kwacha)
PLAN_PRICES = {
    'single':  {'zmw': 75.00,   'label': 'K75'},
    'monthly': {'zmw': 225.00,  'label': 'K225/mo'},
    'annual':  {'zmw': 1800.00, 'label': 'K1,800/yr'},
}

DB_CONFIG = {
    'host':        os.environ.get('DB_HOST',   'localhost'),
    'port':        int(os.environ.get('DB_PORT', 3306)),
    'user':        os.environ.get('DB_USER',   'root'),
    'password':    os.environ.get('DB_PASS',   ''),
    'database':    os.environ.get('DB_NAME',   'smads_african_hits'),
    'charset':     'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor,
    'autocommit':  False,
    'connect_timeout': 10,
}

for d in (UPLOAD_AUDIO, UPLOAD_COVER, UPLOAD_AVATAR):
    os.makedirs(d, exist_ok=True)

app = Flask(__name__, static_folder='.', static_url_path='')
# Fix 2: Warn loudly if the insecure default SECRET_KEY is in use
_secret_key = os.environ.get('SECRET_KEY', '')
if not _secret_key:
    _secret_key = 'smads-zmw-secret-change-in-prod'
    import warnings
    warnings.warn(
        '\n\n⚠️  SECRET_KEY is not set! Using insecure default. '
        'Set the SECRET_KEY environment variable before deploying.\n',
        stacklevel=2
    )
app.secret_key = _secret_key
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)  # Fix 9: Reduced from 30 to 7 days
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True    # JS cannot read session cookie
app.config['MAX_CONTENT_LENGTH'] = (MAX_AUDIO_MB + 20) * 1024 * 1024
app.config['WTF_CSRF_TIME_LIMIT'] = 3600        # token valid for 1 hour
app.config['WTF_CSRF_SSL_STRICT'] = False        # allow HTTP in dev
# Disable Flask-WTF's automatic CSRF enforcement — we handle it manually
# in csrf_protect_api() below, which reads the X-CSRFToken header from JS.
app.config['WTF_CSRF_CHECK_DEFAULT'] = False

# ── Session inactivity timeout ────────────────────────────────────────────────
SESSION_INACTIVITY_MINUTES = int(os.environ.get('SESSION_INACTIVITY_MINUTES', 120))

# ── Security 1: Secure cookie flags (HTTPS-only in production) ────────────────
_is_production = os.environ.get('NODE_ENV') == 'production' or \
                 os.environ.get('FLASK_ENV') == 'production'
app.config['SESSION_COOKIE_SECURE']  = _is_production  # only send over HTTPS
app.config['WTF_CSRF_SSL_STRICT']    = _is_production

# ── Security 2: Allowed hosts (prevent Host header attacks) ──────────────────
ALLOWED_HOSTS = [
    h.strip() for h in
    os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
    if h.strip()
]

# ── Security 3: Input length limits (like Django's max_length) ───────────────
INPUT_LIMITS = {
    'username':     60,
    'email':        120,
    'display_name': 100,
    'password':     128,
    'bio':          1000,
    'website':      255,
    'title':        200,
    'artist_name':  150,
    'genre':        80,
    'mood':         80,
    'region':       80,
    'album':        150,
    'description':  2000,
    'tags':         255,
    'comment_body': 500,
    'name':         100,
    'subject':      200,
    'message':      5000,
    'pin':          10,
    'reason':       100,
}

def limit(value: str, field: str) -> str:
    """Truncate input to the defined max length for the field."""
    max_len = INPUT_LIMITS.get(field, 255)
    return (value or '')[:max_len]

# ── Security 4: Password strength validation ──────────────────────────────────
COMMON_PASSWORDS = {
    'password', 'password1', '123456', '12345678', '1234567890',
    'qwerty', 'abc123', 'letmein', 'welcome', 'monkey', 'dragon',
    'master', 'admin', 'admin123', 'pass', 'test', 'iloveyou',
    'sunshine', 'princess', 'football', 'shadow', 'superman',
}

def validate_password_strength(password: str) -> str | None:
    """Return an error message if password is too weak, else None."""
    if len(password) < 8:
        return 'Password must be at least 8 characters.'
    if password.isdigit():
        return 'Password cannot be all numbers.'
    if password.lower() in COMMON_PASSWORDS:
        return 'Password is too common. Please choose a stronger password.'
    if len(set(password)) < 4:
        return 'Password is too simple. Use a mix of letters and numbers.'
    return None

# ── CSRF Protection ───────────────────────────────────────────────────────────
csrf = CSRFProtect(app)

@app.before_request
def security_checks():
    """Security 2 & 5: Host header validation + Content-Type enforcement + session inactivity."""

    # ── Host header attack prevention ────────────────────────────────────────
    host = request.host.split(':')[0]  # strip port
    if ALLOWED_HOSTS and host not in ALLOWED_HOSTS:
        return jsonify(error='Invalid host.'), 400

    # ── Session inactivity timeout ────────────────────────────────────────────
    if session.get('user_id'):
        last_active = session.get('last_active', 0)
        now = time.time()
        if last_active and (now - last_active) > SESSION_INACTIVITY_MINUTES * 60:
            session.clear()
            if request.path.startswith('/api/'):
                return jsonify(error='Session expired due to inactivity. Please log in again.',
                               session_expired=True), 401
        session['last_active'] = now

    # ── Content-Type enforcement for JSON API endpoints ───────────────────────
    if (request.path.startswith('/api/') and
            request.method == 'POST' and
            request.content_length and
            request.content_length > 0):
        ct = request.content_type or ''
        # Allow multipart (file uploads), form data, and JSON
        if not any(ct.startswith(t) for t in (
            'application/json',
            'application/x-www-form-urlencoded',
            'multipart/form-data',
        )):
            return jsonify(error='Unsupported Content-Type.'), 415

# Exempt API endpoints from cookie-based CSRF — they use header-based token instead
@app.before_request
def csrf_protect_api():
    """For API POST/DELETE/PATCH requests, validate CSRF token from header."""
    if request.path.startswith('/api/') and request.method in ('POST', 'DELETE', 'PATCH', 'PUT'):
        if request.path == '/api/csrf-token':
            return
        token = request.headers.get('X-CSRFToken') or request.form.get('csrf_token')
        if not token:
            return jsonify(error='CSRF token missing. Please refresh the page.'), 403
        try:
            validate_csrf(token)
        except Exception:
            return jsonify(error='Invalid or expired CSRF token. Please refresh the page.'), 403

@app.route('/api/csrf-token')
def get_csrf_token():
    """Return a fresh CSRF token for the frontend to use."""
    return jsonify(csrf_token=generate_csrf())

# ── Security headers ──────────────────────────────────────────────────────────
@app.after_request
def add_security_headers(response):
    # Prevent browsers from sniffing MIME types
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # Block site from being embedded in iframes (clickjacking protection)
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    # Enable browser XSS filter
    response.headers['X-XSS-Protection'] = '1; mode=block'
    # Don't send referrer to external sites
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    # Restrict what resources the page can load (basic CSP)
    response.headers['Content-Security-Policy'] = (
        "default-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com "
        "https://picsum.photos https://via.placeholder.com; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "img-src 'self' data: https://picsum.photos https://via.placeholder.com blob:; "
        "media-src 'self' blob:; "
        "connect-src 'self';"
    )
    # HTTPS only (active when behind SSL proxy)
    if os.environ.get('HTTPS_ENABLED'):
        response.headers['Strict-Transport-Security'] = (
            'max-age=31536000; includeSubDomains')
    # Hide Flask/Werkzeug version
    response.headers['Server'] = 'SMADS'
    return response

# ── JSON error handlers (prevent HTML error pages breaking the frontend) ─────
@app.errorhandler(400)
def err_400(e): return jsonify(error='Bad request.'), 400

@app.errorhandler(401)
def err_401(e): return jsonify(error='Authentication required.'), 401

@app.errorhandler(403)
def err_403(e): return jsonify(error='Forbidden.'), 403

@app.errorhandler(404)
def err_404(e):
    # Serve the custom 404 page for browser requests, JSON for API calls
    if request.path.startswith('/api/'):
        return jsonify(error='Not found.'), 404
    return send_from_directory('.', '404.html'), 404

@app.errorhandler(405)
def err_405(e): return jsonify(error='Method not allowed.'), 405

@app.errorhandler(413)
def err_413(e): return jsonify(error='File too large.'), 413

@app.errorhandler(429)
def err_429(e): return jsonify(error='Too many requests. Please slow down.'), 429

@app.errorhandler(500)
def err_500(e):
    app.logger.error('Internal server error: %s', e)
    return jsonify(error='Something went wrong on our end. Please try again.'), 500

@app.errorhandler(Exception)
def err_unhandled(e):
    app.logger.exception('Unhandled exception')
    return jsonify(error='Something went wrong on our end. Please try again.'), 500

# ── MIME type signatures for file validation ──────────────────────────────────
# First bytes (magic numbers) of valid file types
AUDIO_MIME_SIGNATURES = {
    b'\xff\xfb': 'mp3', b'\xff\xf3': 'mp3', b'\xff\xf2': 'mp3',
    b'ID3':      'mp3',
    b'RIFF':     'wav',   # WAV starts with RIFF
    b'fLaC':     'flac',
    b'\xff\xf1': 'aac',  b'\xff\xf9': 'aac',
    b'OggS':     'ogg',
}
IMAGE_MIME_SIGNATURES = {
    b'\xff\xd8\xff':    'jpeg',
    b'\x89PNG\r\n':     'png',
    b'GIF87a':          'gif',
    b'GIF89a':          'gif',
    b'RIFF':            'webp',  # WEBP starts with RIFF....WEBP
}

def validate_audio_mime(file_storage) -> bool:
    """Read first 12 bytes and check against known audio magic numbers."""
    header = file_storage.read(12)
    file_storage.seek(0)  # reset for later saving
    for sig, _ in AUDIO_MIME_SIGNATURES.items():
        if header[:len(sig)] == sig:
            # Extra check: RIFF could be WAV or WEBP — confirm WAV
            if sig == b'RIFF':
                return header[8:12] == b'WAVE'
            return True
    return False

def validate_image_mime(file_storage) -> bool:
    """Read first 12 bytes and check against known image magic numbers."""
    header = file_storage.read(12)
    file_storage.seek(0)
    for sig, _ in IMAGE_MIME_SIGNATURES.items():
        if header[:len(sig)] == sig:
            if sig == b'RIFF':
                return header[8:12] == b'WEBP'
            return True
    return False

# ── Email alert config ────────────────────────────────────────────────────────
ALERT_EMAIL_TO   = os.environ.get('ALERT_EMAIL_TO',   '')   # your email
ALERT_EMAIL_FROM = os.environ.get('ALERT_EMAIL_FROM', '')
ALERT_SMTP_HOST  = os.environ.get('ALERT_SMTP_HOST',  'smtp.gmail.com')
ALERT_SMTP_PORT  = int(os.environ.get('ALERT_SMTP_PORT', 587))
ALERT_SMTP_USER  = os.environ.get('ALERT_SMTP_USER',  '')
ALERT_SMTP_PASS  = os.environ.get('ALERT_SMTP_PASS',  '')

def send_alert_email(subject: str, body: str):
    """Send a security alert email in a background thread (non-blocking)."""
    if not all([ALERT_EMAIL_TO, ALERT_SMTP_USER, ALERT_SMTP_PASS]):
        return  # Email not configured — skip silently
    def _send():
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f'[SMADS SECURITY] {subject}'
            msg['From']    = ALERT_EMAIL_FROM or ALERT_SMTP_USER
            msg['To']      = ALERT_EMAIL_TO
            msg.attach(MIMEText(body, 'plain'))
            with smtplib.SMTP(ALERT_SMTP_HOST, ALERT_SMTP_PORT) as server:
                server.ehlo()
                server.starttls()
                server.login(ALERT_SMTP_USER, ALERT_SMTP_PASS)
                server.sendmail(msg['From'], [ALERT_EMAIL_TO], msg.as_string())
        except Exception as e:
            print(f'[SMADS] Alert email failed: {e}')
    threading.Thread(target=_send, daemon=True).start()

def send_email(to: str, subject: str, body_text: str, body_html: str = ''):
    """Send a transactional email (verification, notifications) in background."""
    if not all([ALERT_SMTP_USER, ALERT_SMTP_PASS]):
        print(f'[SMADS] Email not configured — would send to {to}: {subject}')
        return
    def _send():
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From']    = ALERT_EMAIL_FROM or ALERT_SMTP_USER
            msg['To']      = to
            msg.attach(MIMEText(body_text, 'plain'))
            if body_html:
                msg.attach(MIMEText(body_html, 'html'))
            with smtplib.SMTP(ALERT_SMTP_HOST, ALERT_SMTP_PORT) as server:
                server.ehlo()
                server.starttls()
                server.login(ALERT_SMTP_USER, ALERT_SMTP_PASS)
                server.sendmail(msg['From'], [to], msg.as_string())
        except Exception as e:
            print(f'[SMADS] Email to {to} failed: {e}')
    threading.Thread(target=_send, daemon=True).start()

# ── Site base URL (for email links) ──────────────────────────────────────────
SITE_URL = os.environ.get('SITE_URL', 'http://localhost:5000')

# ── Login rate limiter (in-memory, per IP) ────────────────────────────────────
# Fix 5: Note — these are in-memory and reset on server restart.
# For production, replace with Redis-backed storage (e.g. flask-limiter with Redis).
# Tracks: { ip: {'attempts': int, 'locked_until': float} }
_login_attempts: dict = defaultdict(lambda: {'attempts': 0, 'locked_until': 0.0})
_login_lock = threading.Lock()

LOGIN_MAX_ATTEMPTS  = 5          # failed attempts before lockout
LOGIN_LOCKOUT_SECS  = 15 * 60   # 15-minute lockout
LOGIN_WINDOW_SECS   = 10 * 60   # reset attempt counter after 10 min of no attempts

def _get_client_ip() -> str:
    """Return the real client IP.
    Fix 4: Only trust X-Forwarded-For when TRUST_PROXY env var is set,
    preventing clients from spoofing their IP to bypass rate limiting.
    """
    if os.environ.get('TRUST_PROXY'):
        forwarded = request.headers.get('X-Forwarded-For', '')
        if forwarded:
            return forwarded.split(',')[0].strip()
    return request.remote_addr or '0.0.0.0'

def _check_rate_limit(ip: str):
    """Raise a 429 response if the IP is locked out."""
    with _login_lock:
        record = _login_attempts[ip]
        now = time.time()
        if record['locked_until'] > now:
            remaining = int(record['locked_until'] - now)
            mins, secs = divmod(remaining, 60)
            raise _RateLimitError(
                f'Too many failed login attempts. Try again in {mins}m {secs}s.')

def _record_failed_login(ip: str):
    """Increment failure counter; lock the IP after too many attempts."""
    with _login_lock:
        record = _login_attempts[ip]
        now = time.time()
        record['attempts'] += 1
        if record['attempts'] >= LOGIN_MAX_ATTEMPTS:
            record['locked_until'] = now + LOGIN_LOCKOUT_SECS
            record['attempts'] = 0  # reset so counter is clean after lockout
            # Send alert email in background
            send_alert_email(
                f'Brute-force login attempt blocked — IP {ip}',
                f'IP address {ip} has been locked out after {LOGIN_MAX_ATTEMPTS} '
                f'failed login attempts on SMADS African Hits.\n\n'
                f'Lockout duration: {LOGIN_LOCKOUT_SECS // 60} minutes.\n'
                f'Time: {time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())}\n\n'
                f'If this was not you, consider blocking this IP in your firewall.'
            )

def _clear_login_attempts(ip: str):
    """Clear failure counter on successful login."""
    with _login_lock:
        _login_attempts.pop(ip, None)

class _RateLimitError(Exception):
    def __init__(self, message):
        self.message = message

# ── Per-account login rate limiter ────────────────────────────────────────────
# Separate from IP limiter — catches distributed attacks targeting one account
_account_attempts: dict = defaultdict(lambda: {'attempts': 0, 'locked_until': 0.0})
ACCOUNT_MAX_ATTEMPTS = 10       # more lenient than IP (same user, different IPs)
ACCOUNT_LOCKOUT_SECS = 30 * 60  # 30-minute lockout per account

def _check_account_rate_limit(user_id: int):
    with _login_lock:
        record = _account_attempts[user_id]
        now = time.time()
        if record['locked_until'] > now:
            remaining = int(record['locked_until'] - now)
            mins, secs = divmod(remaining, 60)
            raise _RateLimitError(
                f'Too many failed attempts on this account. Try again in {mins}m {secs}s.')

def _record_account_failed_login(user_id: int):
    with _login_lock:
        record = _account_attempts[user_id]
        now = time.time()
        record['attempts'] += 1
        if record['attempts'] >= ACCOUNT_MAX_ATTEMPTS:
            record['locked_until'] = now + ACCOUNT_LOCKOUT_SECS
            record['attempts'] = 0
            send_alert_email(
                f'Account brute-force detected — user ID {user_id}',
                f'User account ID {user_id} has been locked after {ACCOUNT_MAX_ATTEMPTS} '
                f'failed login attempts from multiple IPs.\n\n'
                f'Time: {time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())}\n\n'
                f'This may indicate a distributed brute-force attack.'
            )

def _clear_account_login_attempts(user_id: int):
    with _login_lock:
        _account_attempts.pop(user_id, None)

# ── DB helpers ────────────────────────────────────────────────────────────────
def get_db():
    return pymysql.connect(**DB_CONFIG)

def init_db():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            # Users
            cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            INT AUTO_INCREMENT PRIMARY KEY,
                username      VARCHAR(60)  UNIQUE NOT NULL,
                email         VARCHAR(120) UNIQUE NOT NULL,
                display_name  VARCHAR(100) NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                role          VARCHAR(20)  DEFAULT 'listener',
                avatar_url    VARCHAR(255),
                bio           TEXT,
                website       VARCHAR(255),
                country       VARCHAR(60)  DEFAULT 'Zambia',
                is_active     TINYINT(1)   DEFAULT 1,
                is_admin      TINYINT(1)   DEFAULT 0,
                is_verified   TINYINT(1)   DEFAULT 0,
                email_verified     TINYINT(1)   DEFAULT 0,
                email_verify_token VARCHAR(64)  NULL,
                created_at    DATETIME     DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            # Tracks
            cur.execute("""
            CREATE TABLE IF NOT EXISTS tracks (
                id            INT AUTO_INCREMENT PRIMARY KEY,
                user_id       INT          NOT NULL,
                title         VARCHAR(200) NOT NULL,
                artist_name   VARCHAR(150) NOT NULL,
                genre         VARCHAR(80)  NOT NULL,
                mood          VARCHAR(80),
                region        VARCHAR(80),
                album         VARCHAR(150),
                description   TEXT,
                tags          VARCHAR(255),
                audio_url     VARCHAR(255) NOT NULL,
                cover_url     VARCHAR(255),
                duration      INT          DEFAULT 0,
                plays         INT          DEFAULT 0,
                downloads     INT          DEFAULT 0,
                likes_count   INT          DEFAULT 0,
                shares        INT          DEFAULT 0,
                is_free_dl    TINYINT(1)   DEFAULT 1,
                status        VARCHAR(20)  DEFAULT 'published',
                chart_score   DECIMAL(10,2) DEFAULT 0,
                created_at    DATETIME     DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            # Likes
            cur.execute("""
            CREATE TABLE IF NOT EXISTS likes (
                user_id   INT NOT NULL,
                track_id  INT NOT NULL,
                PRIMARY KEY (user_id, track_id),
                FOREIGN KEY (user_id)  REFERENCES users(id)  ON DELETE CASCADE,
                FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
            ) ENGINE=InnoDB;
            """)
            # Comments
            cur.execute("""
            CREATE TABLE IF NOT EXISTS comments (
                id         INT AUTO_INCREMENT PRIMARY KEY,
                track_id   INT  NOT NULL,
                user_id    INT  NOT NULL,
                body       TEXT NOT NULL,
                likes      INT  DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id)  REFERENCES users(id)  ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            # Playlists
            cur.execute("""
            CREATE TABLE IF NOT EXISTS playlists (
                id          INT AUTO_INCREMENT PRIMARY KEY,
                user_id     INT          NOT NULL,
                name        VARCHAR(150) NOT NULL,
                description TEXT,
                is_public   TINYINT(1)   DEFAULT 1,
                created_at  DATETIME     DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            # Playlist tracks
            cur.execute("""
            CREATE TABLE IF NOT EXISTS playlist_tracks (
                playlist_id INT NOT NULL,
                track_id    INT NOT NULL,
                position    INT DEFAULT 0,
                PRIMARY KEY (playlist_id, track_id),
                FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
                FOREIGN KEY (track_id)    REFERENCES tracks(id)    ON DELETE CASCADE
            ) ENGINE=InnoDB;
            """)
            # Follows
            cur.execute("""
            CREATE TABLE IF NOT EXISTS follows (
                follower_id INT NOT NULL,
                target_id   INT NOT NULL,
                PRIMARY KEY (follower_id, target_id),
                FOREIGN KEY (follower_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (target_id)   REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB;
            """)
            # Payments (ZMW)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id         INT AUTO_INCREMENT PRIMARY KEY,
                user_id    INT          NOT NULL,
                plan       VARCHAR(30)  NOT NULL,
                amount_zmw DECIMAL(10,2) NOT NULL,
                method     VARCHAR(50)  DEFAULT 'card',
                status     VARCHAR(20)  DEFAULT 'pending',
                reference  VARCHAR(64),
                created_at DATETIME     DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            # Reports
            cur.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id          INT AUTO_INCREMENT PRIMARY KEY,
                reporter_id INT NOT NULL,
                track_id    INT,
                reason      VARCHAR(100) NOT NULL,
                details     TEXT,
                status      VARCHAR(20)  DEFAULT 'pending',
                created_at  DATETIME     DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (reporter_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (track_id)    REFERENCES tracks(id) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            # Play history (for analytics)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS play_history (
                id         INT AUTO_INCREMENT PRIMARY KEY,
                track_id   INT NOT NULL,
                user_id    INT,
                country    VARCHAR(60),
                played_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
            ) ENGINE=InnoDB;
            """)
            # Contact messages
            cur.execute("""
            CREATE TABLE IF NOT EXISTS contact_messages (
                id         INT AUTO_INCREMENT PRIMARY KEY,
                name       VARCHAR(100),
                email      VARCHAR(120),
                subject    VARCHAR(200),
                message    TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            # Admin settings (PIN and other config)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS admin_settings (
                key_name   VARCHAR(60) PRIMARY KEY,
                value      VARCHAR(255) NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            # Seed default admin PIN (7000001) — stored as bcrypt hash
            cur.execute("SELECT key_name FROM admin_settings WHERE key_name='admin_pin'")
            if not cur.fetchone():
                cur.execute(
                    "INSERT INTO admin_settings (key_name, value) VALUES (%s, %s)",
                    ('admin_pin', generate_password_hash('7000001')))
            # Admin PIN attempt tracker table
            cur.execute("""
            CREATE TABLE IF NOT EXISTS admin_pin_attempts (
                id           INT AUTO_INCREMENT PRIMARY KEY,
                user_id      INT NOT NULL,
                attempts     INT DEFAULT 0,
                locked_until DATETIME NULL,
                updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_user (user_id)
            ) ENGINE=InnoDB;
            """)
            # Password reset tokens
            cur.execute("""
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id         INT AUTO_INCREMENT PRIMARY KEY,
                user_id    INT NOT NULL,
                token_hash VARCHAR(64) NOT NULL UNIQUE,
                expires_at DATETIME NOT NULL,
                used       TINYINT(1) DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_token (token_hash),
                INDEX idx_user (user_id)
            ) ENGINE=InnoDB;
            """)
            # Login history (last 20 logins per user)
            cur.execute("""
            CREATE TABLE IF NOT EXISTS login_history (
                id         INT AUTO_INCREMENT PRIMARY KEY,
                user_id    INT NOT NULL,
                ip_address VARCHAR(45) NOT NULL,
                user_agent VARCHAR(255),
                status     ENUM('success','failed','blocked') NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_user_time (user_id, created_at DESC)
            ) ENGINE=InnoDB;
            """)
            # Active sessions tracker (for "log out all devices")
            cur.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                id           INT AUTO_INCREMENT PRIMARY KEY,
                user_id      INT NOT NULL,
                session_id   VARCHAR(64) NOT NULL UNIQUE,
                ip_address   VARCHAR(45),
                user_agent   VARCHAR(255),
                last_active  DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                INDEX idx_user (user_id),
                INDEX idx_session (session_id)
            ) ENGINE=InnoDB;
            """)
            # Indexes
            for idx in [
                "CREATE INDEX idx_tracks_genre   ON tracks(genre)",
                "CREATE INDEX idx_tracks_plays   ON tracks(plays)",
                "CREATE INDEX idx_tracks_score   ON tracks(chart_score)",
                "CREATE INDEX idx_tracks_created ON tracks(created_at)",
                "CREATE INDEX idx_tracks_user    ON tracks(user_id)",
                "CREATE INDEX idx_play_history   ON play_history(track_id, played_at)",
            ]:
                try:
                    cur.execute(idx)
                except Exception:
                    pass  # Already exists

            # ── Schema migrations (add columns that may be missing from older DBs) ──
            migrations = [
                "ALTER TABLE users ADD COLUMN email_verified     TINYINT(1)  DEFAULT 0   AFTER is_verified",
                "ALTER TABLE users ADD COLUMN email_verify_token VARCHAR(64) NULL        AFTER email_verified",
                "ALTER TABLE users ADD COLUMN website            VARCHAR(255)            AFTER bio",
                "ALTER TABLE users ADD COLUMN country            VARCHAR(60) DEFAULT 'Zambia' AFTER website",
                "ALTER TABLE tracks ADD COLUMN shares            INT         DEFAULT 0   AFTER likes_count",
                "ALTER TABLE tracks ADD COLUMN chart_score       DECIMAL(10,2) DEFAULT 0 AFTER shares",
                "ALTER TABLE payments ADD COLUMN plan_expires_at DATETIME NULL           AFTER status",
            ]
            for migration in migrations:
                try:
                    cur.execute(migration)
                except Exception:
                    pass  # Column already exists — safe to ignore

            # Seed admin — Fix 3: Use a random password that must be changed on first login
            cur.execute("SELECT id FROM users WHERE email='admin@smadsafricanhits.com'")
            if not cur.fetchone():
                _admin_pass = os.environ.get('ADMIN_INITIAL_PASSWORD', '')
                if not _admin_pass:
                    # Generate a random password and print it once — admin must change it
                    _admin_pass = secrets.token_urlsafe(16)
                    print(f'\n🔑 Admin account created. Initial password: {_admin_pass}')
                    print('   Change this immediately after first login!\n')
                cur.execute(
                    "INSERT INTO users (username,email,display_name,password_hash,role,is_admin,is_verified,country) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    ('admin', 'admin@smadsafricanhits.com', 'SMADS Admin',
                     generate_password_hash(_admin_pass), 'artist', 1, 1, 'Zambia'))
        conn.commit()
    finally:
        conn.close()

try:
    init_db()
    print("✅ SMADS DB ready")
except Exception as e:
    print(f"⚠️  DB init skipped: {e} — start MySQL in XAMPP first")

# ── Helpers ───────────────────────────────────────────────────────────────────
def current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    try:
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT * FROM users WHERE id=%s AND is_active=1', (uid,))
                return cur.fetchone()
        finally:
            conn.close()
    except Exception:
        return None

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        u = current_user()
        if not u:
            return jsonify(error='Authentication required'), 401
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        u = current_user()
        if not u or not u['is_admin']:
            return jsonify(error='Admin access required'), 403
        # PIN must be verified in this session
        if not session.get('pin_verified'):
            return jsonify(error='Admin PIN verification required', pin_required=True), 403
        return f(*args, **kwargs)
    return decorated

def allowed_file(filename, allowed):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed

def user_dict(u):
    return {
        'id': u['id'], 'username': u['username'], 'email': u['email'],
        'display_name': u['display_name'], 'role': u['role'],
        'avatar_url': u['avatar_url'], 'bio': u['bio'],
        'country': u.get('country', 'Zambia'),
        'is_admin': bool(u['is_admin']),
        'is_verified': bool(u.get('is_verified', 0)),
        'email_verified': bool(u.get('email_verified', 0)),
        'created_at': str(u['created_at']),
    }

def track_dict(t, liked=False):
    return {
        'id': t['id'], 'title': t['title'], 'artist_name': t['artist_name'],
        'genre': t['genre'], 'mood': t.get('mood'), 'region': t.get('region'),
        'album': t['album'], 'description': t['description'],
        'audio_url': t['audio_url'], 'cover_url': t['cover_url'],
        'duration': t['duration'], 'plays': t['plays'],
        'downloads': t['downloads'], 'shares': t.get('shares', 0),
        'is_free_dl': bool(t['is_free_dl']), 'status': t['status'],
        'created_at': str(t['created_at']), 'user_id': t['user_id'],
        'likes': t.get('likes', t.get('likes_count', 0)),
        'chart_score': float(t.get('chart_score', 0)),
        'user_liked': liked,
    }

def recalc_chart_score(cur, track_id):
    """Score = downloads*3 + plays*1 + likes*2 + shares*4 (recency weighted)."""
    cur.execute("""
        UPDATE tracks SET chart_score =
            (downloads * 3) + (plays * 1) + (likes_count * 2) + (shares * 4)
        WHERE id=%s
    """, (track_id,))

# ── Static files ──────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:filename>')
def static_files(filename):
    if filename.startswith('api/'):
        abort(404)
    # ── Admin page protection ─────────────────────────────────────────────────
    # admin.html is only served to logged-in admin users.
    # Anyone else gets redirected to the homepage.
    if filename in ('admin.html', 'admin'):
        u = current_user()
        if not u or not u.get('is_admin'):
            # Return a plain redirect — don't reveal the page exists
            from flask import redirect
            return redirect('/', code=302)
    response = send_from_directory('.', filename)
    # Prevent browser from caching auth-sensitive pages
    if filename in ('profile.html', 'upload.html', 'admin.html'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
    return response

@app.route('/uploads/audio/<path:filename>')
def serve_audio(filename):
    return send_from_directory(UPLOAD_AUDIO, filename)

@app.route('/uploads/covers/<path:filename>')
def serve_cover(filename):
    return send_from_directory(UPLOAD_COVER, filename)

@app.route('/uploads/avatars/<path:filename>')
def serve_avatar(filename):
    return send_from_directory(UPLOAD_AVATAR, filename)

# ── Auth API ──────────────────────────────────────────────────────────────────
@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    d            = request.form
    username     = limit((d.get('username') or '').strip().lower(), 'username')
    email        = limit((d.get('email') or '').strip().lower(), 'email')
    display_name = limit((d.get('display_name') or '').strip(), 'display_name')
    password     = (d.get('password') or '')[:128]
    role         = d.get('role', 'listener')
    country      = limit((d.get('country') or 'Zambia').strip(), 'region')

    if not all([username, email, display_name, password]):
        return jsonify(error='All fields are required'), 400

    # Fix 1: Validate email format
    if '@' not in email or '.' not in email.split('@')[-1]:
        return jsonify(error='Please enter a valid email address'), 400

    # Fix 2: Reject whitespace-only display_name
    if not display_name.strip():
        return jsonify(error='Display name cannot be blank'), 400

    # Username must be alphanumeric + underscores/hyphens only
    import re as _re
    if not _re.match(r'^[a-z0-9_\-]{3,60}$', username):
        return jsonify(error='Username must be 3–60 characters: letters, numbers, _ or - only'), 400

    # Password strength validation (Security 4)
    pw_error = validate_password_strength(password)
    if pw_error:
        return jsonify(error=pw_error), 400

    if role not in ('listener', 'artist'):
        role = 'listener'

    # Generate email verification token
    verify_token = secrets.token_urlsafe(32)

    conn = get_db()
    user = None
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT id FROM users WHERE username=%s', (username,))
            if cur.fetchone():
                return jsonify(error='Username already taken'), 409
            cur.execute('SELECT id FROM users WHERE email=%s', (email,))
            if cur.fetchone():
                return jsonify(error='Email already registered'), 409
            cur.execute(
                'INSERT INTO users '
                '(username,email,display_name,password_hash,role,country,'
                ' email_verified,email_verify_token) '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                (username, email, display_name,
                 generate_password_hash(password), role, country,
                 0, verify_token))
            new_id = cur.lastrowid
            conn.commit()
            cur.execute('SELECT * FROM users WHERE id=%s', (new_id,))
            user = cur.fetchone()
    except Exception as e:
        app.logger.error('Registration DB error: %s', e)
        return jsonify(error='Registration failed. Please try again.'), 500
    finally:
        conn.close()

    if not user:
        app.logger.error('Registration: user not found after insert (id=%s)', locals().get('new_id'))
        return jsonify(error='Registration failed. Please try again.'), 500

    # Send verification email
    verify_url = f'{SITE_URL}/api/auth/verify_email?token={verify_token}'
    send_email(
        to=email,
        subject='Verify your SMADS African Hits account',
        body_text=(
            f'Hi {display_name},\n\n'
            f'Welcome to SMADS African Hits!\n\n'
            f'Please verify your email address by clicking the link below:\n'
            f'{verify_url}\n\n'
            f'This link expires in 48 hours.\n\n'
            f'If you did not create this account, ignore this email.\n\n'
            f'— SMADS African Hits Team'
        ),
        body_html=(
            f'<h2>Welcome to SMADS African Hits, {display_name}!</h2>'
            f'<p>Please verify your email address to activate your account.</p>'
            f'<p><a href="{verify_url}" style="background:#6c63ff;color:#fff;'
            f'padding:12px 24px;border-radius:50px;text-decoration:none;'
            f'font-weight:bold">Verify Email Address</a></p>'
            f'<p style="color:#999;font-size:12px">Link expires in 48 hours. '
            f'If you did not register, ignore this email.</p>'
        )
    )

    session.clear()   # session fixation protection
    session.permanent = True
    session['user_id'] = user['id']
    return jsonify(
        user=user_dict(user),
        message='Account created! Please check your email to verify your address.'
    ), 201


@app.route('/api/auth/verify_email')
def auth_verify_email():
    """Clicked from the verification email link."""
    token = request.args.get('token', '').strip()
    if not token:
        return '<h2>Invalid verification link.</h2>', 400
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT id, display_name, email_verified FROM users '
                'WHERE email_verify_token=%s', (token,))
            user = cur.fetchone()
            if not user:
                return '<h2>Invalid or expired verification link.</h2>', 400
            if user['email_verified']:
                return '''<html><body style="font-family:sans-serif;text-align:center;padding:4rem;background:#0d0d1a;color:#fff">
                    <h2 style="color:#43e97b">✓ Already Verified</h2>
                    <p>Your email is already verified.</p>
                    <a href="/" style="color:#6c63ff">Go to SMADS African Hits</a>
                    </body></html>'''
            cur.execute(
                'UPDATE users SET email_verified=1, email_verify_token=NULL WHERE id=%s',
                (user['id'],))
        conn.commit()
    finally:
        conn.close()
    return '''<html><body style="font-family:sans-serif;text-align:center;padding:4rem;background:#0d0d1a;color:#fff">
        <div style="font-size:3rem;margin-bottom:1rem">🎉</div>
        <h2 style="color:#43e97b">Email Verified!</h2>
        <p style="color:#a0a0c0;margin-bottom:2rem">Your account is now fully active. You can now upload music.</p>
        <a href="/" style="background:#6c63ff;color:#fff;padding:12px 24px;border-radius:50px;text-decoration:none;font-weight:bold">
            Go to SMADS African Hits
        </a>
        </body></html>'''


@app.route('/api/auth/resend_verification', methods=['POST'])
@login_required
def auth_resend_verification():
    """Resend the verification email. Rate-limited to 3 attempts per hour per user."""
    uid = session['user_id']
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM users WHERE id=%s AND is_active=1', (uid,))
            u = cur.fetchone()
            if not u:
                return jsonify(error='User not found'), 404
            if u['email_verified']:
                return jsonify(error='Your email is already verified.'), 400

            # ── Rate limit: max 3 resends per hour ────────────────────────────
            cur.execute(
                "SELECT COUNT(*) AS c FROM login_history "
                "WHERE user_id=%s AND status='resend_verify' "
                "AND created_at >= DATE_SUB(NOW(), INTERVAL 1 HOUR)",
                (uid,))
            resend_count = cur.fetchone()['c']
            if resend_count >= 3:
                return jsonify(
                    error='Too many verification emails sent. Please wait an hour before trying again.'
                ), 429

            token = secrets.token_urlsafe(32)
            cur.execute(
                'UPDATE users SET email_verify_token=%s WHERE id=%s',
                (token, uid))
            # Record this resend attempt in login_history for rate limiting
            cur.execute(
                'INSERT INTO login_history (user_id, ip_address, user_agent, status) '
                'VALUES (%s, %s, %s, %s)',
                (uid, _get_client_ip(),
                 request.headers.get('User-Agent', '')[:255], 'resend_verify'))
        conn.commit()
    finally:
        conn.close()
    verify_url = f'{SITE_URL}/api/auth/verify_email?token={token}'
    send_email(
        to=u['email'],
        subject='Verify your SMADS African Hits account',
        body_text=(
            f'Hi {u["display_name"]},\n\n'
            f'Here is your new verification link:\n{verify_url}\n\n'
            f'— SMADS African Hits Team'
        )
    )
    return jsonify(message='Verification email resent. Please check your inbox.')


# ── Password Reset ────────────────────────────────────────────────────────────
PASSWORD_RESET_EXPIRY_MINUTES = 30

@app.route('/api/auth/forgot_password', methods=['POST'])
def auth_forgot_password():
    """Request a password reset email. Always returns success to prevent email enumeration."""
    email = limit((request.form.get('email') or '').strip().lower(), 'email')
    if not email or '@' not in email:
        return jsonify(message='If that email exists, a reset link has been sent.'), 200

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT id, display_name, is_active FROM users WHERE email=%s', (email,))
            user = cur.fetchone()
            if user and user['is_active']:
                # Invalidate any existing unused tokens for this user
                cur.execute(
                    'UPDATE password_reset_tokens SET used=1 WHERE user_id=%s AND used=0',
                    (user['id'],))
                # Generate new token
                raw_token  = secrets.token_urlsafe(32)
                token_hash = __import__('hashlib').sha256(raw_token.encode()).hexdigest()
                import datetime
                expires_at = datetime.datetime.now() + \
                             datetime.timedelta(minutes=PASSWORD_RESET_EXPIRY_MINUTES)
                cur.execute(
                    'INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) '
                    'VALUES (%s, %s, %s)',
                    (user['id'], token_hash, expires_at))
                conn.commit()
                reset_url = f'{SITE_URL}/reset-password.html?token={raw_token}'
                send_email(
                    to=email,
                    subject='Reset your SMADS African Hits password',
                    body_text=(
                        f'Hi {user["display_name"]},\n\n'
                        f'You requested a password reset. Click the link below:\n'
                        f'{reset_url}\n\n'
                        f'This link expires in {PASSWORD_RESET_EXPIRY_MINUTES} minutes.\n\n'
                        f'If you did not request this, ignore this email — your password is unchanged.\n\n'
                        f'— SMADS African Hits Team'
                    ),
                    body_html=(
                        f'<h2>Password Reset</h2>'
                        f'<p>Hi {user["display_name"]},</p>'
                        f'<p>Click the button below to reset your password. '
                        f'This link expires in {PASSWORD_RESET_EXPIRY_MINUTES} minutes.</p>'
                        f'<p><a href="{reset_url}" style="background:#6c63ff;color:#fff;'
                        f'padding:12px 24px;border-radius:50px;text-decoration:none;'
                        f'font-weight:bold">Reset Password</a></p>'
                        f'<p style="color:#999;font-size:12px">If you did not request this, '
                        f'ignore this email.</p>'
                    )
                )
    finally:
        conn.close()
    # Always return the same message — prevents email enumeration
    return jsonify(message='If that email exists, a reset link has been sent.')


@app.route('/api/auth/reset_password', methods=['POST'])
def auth_reset_password():
    """Reset password using a valid token."""
    raw_token    = (request.form.get('token') or '').strip()
    new_password = (request.form.get('password') or '')[:128]

    if not raw_token or not new_password:
        return jsonify(error='Token and new password are required'), 400

    pw_error = validate_password_strength(new_password)
    if pw_error:
        return jsonify(error=pw_error), 400

    import hashlib, datetime
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT * FROM password_reset_tokens '
                'WHERE token_hash=%s AND used=0 AND expires_at > NOW()',
                (token_hash,))
            token_row = cur.fetchone()
            if not token_row:
                return jsonify(error='Invalid or expired reset link. Please request a new one.'), 400

            # Mark token as used
            cur.execute('UPDATE password_reset_tokens SET used=1 WHERE id=%s', (token_row['id'],))
            # Update password
            cur.execute(
                'UPDATE users SET password_hash=%s WHERE id=%s',
                (generate_password_hash(new_password), token_row['user_id']))
            # Invalidate all active sessions for this user (force re-login everywhere)
            cur.execute('DELETE FROM user_sessions WHERE user_id=%s', (token_row['user_id'],))
        conn.commit()
    finally:
        conn.close()

    return jsonify(message='Password reset successfully. Please log in with your new password.')


@app.route('/api/auth/login_history')
@login_required
def auth_login_history():
    """Return the last 20 login attempts for the current user."""
    uid = session['user_id']
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT ip_address, user_agent, status, created_at '
                'FROM login_history WHERE user_id=%s '
                'ORDER BY created_at DESC LIMIT 20',
                (uid,))
            rows = cur.fetchall()
    finally:
        conn.close()
    return jsonify(history=[{
        'ip': r['ip_address'],
        'device': _parse_user_agent(r['user_agent'] or ''),
        'status': r['status'],
        'time': str(r['created_at']),
    } for r in rows])


@app.route('/api/auth/sessions')
@login_required
def auth_sessions():
    """Return all active sessions for the current user."""
    uid = session['user_id']
    current_sid = session.get('session_id', '')
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT session_id, ip_address, user_agent, last_active, created_at '
                'FROM user_sessions WHERE user_id=%s ORDER BY last_active DESC',
                (uid,))
            rows = cur.fetchall()
    finally:
        conn.close()
    return jsonify(sessions=[{
        'is_current': r['session_id'] == current_sid,
        'ip': r['ip_address'],
        'device': _parse_user_agent(r['user_agent'] or ''),
        'last_active': str(r['last_active']),
        'created_at': str(r['created_at']),
    } for r in rows])


@app.route('/api/auth/logout_all', methods=['POST'])
@login_required
def auth_logout_all():
    """Log out from all devices."""
    uid = session['user_id']
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM user_sessions WHERE user_id=%s', (uid,))
        conn.commit()
    finally:
        conn.close()
    session.clear()
    return jsonify(message='Logged out from all devices.')


def _parse_user_agent(ua: str) -> str:
    """Return a human-readable device description from User-Agent string."""
    ua_lower = ua.lower()
    if 'mobile' in ua_lower or 'android' in ua_lower:
        device = 'Mobile'
    elif 'tablet' in ua_lower or 'ipad' in ua_lower:
        device = 'Tablet'
    else:
        device = 'Desktop'
    if 'chrome' in ua_lower:
        browser = 'Chrome'
    elif 'firefox' in ua_lower:
        browser = 'Firefox'
    elif 'safari' in ua_lower:
        browser = 'Safari'
    elif 'edge' in ua_lower:
        browser = 'Edge'
    else:
        browser = 'Browser'
    if 'windows' in ua_lower:
        os_name = 'Windows'
    elif 'mac' in ua_lower:
        os_name = 'Mac'
    elif 'android' in ua_lower:
        os_name = 'Android'
    elif 'iphone' in ua_lower or 'ios' in ua_lower:
        os_name = 'iOS'
    elif 'linux' in ua_lower:
        os_name = 'Linux'
    else:
        os_name = 'Unknown OS'
    return f'{device} · {browser} on {os_name}'

@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    d        = request.form
    login    = limit((d.get('login') or '').strip().lower(), 'email')
    password = (d.get('password') or '')[:128]
    ip       = _get_client_ip()

    if not login or not password:
        return jsonify(error='Email/username and password required'), 400

    # ── IP-based rate limit check ─────────────────────────────────────────────
    try:
        _check_rate_limit(ip)
    except _RateLimitError as e:
        return jsonify(error=e.message), 429

    conn = get_db()
    try:
        with conn.cursor() as cur:
            # Fetch user regardless of is_active to give correct error messages
            cur.execute(
                'SELECT * FROM users WHERE (email=%s OR username=%s)',
                (login, login))
            user = cur.fetchone()
    finally:
        conn.close()

    # ── Timing-safe check — always run password hash even if user not found ──
    # This prevents timing attacks that reveal whether an email exists
    dummy_hash = '$2b$12$invalidhashpaddingtomatchbcryptlength000000000000000000'
    check_hash = user['password_hash'] if user else dummy_hash
    password_ok = check_password_hash(check_hash, password)

    # ── Fix 3: Check suspended BEFORE recording failed attempts ─────────────
    # A suspended user should not pollute rate-limit counters
    if user and not user['is_active']:
        return jsonify(error='Your account has been suspended. Contact support.'), 403

    if not user or not password_ok:
        _record_failed_login(ip)
        # Also record per-account failed attempt if user exists
        if user:
            _record_account_failed_login(user['id'])
            # Log failed attempt to history
            try:
                ua = request.headers.get('User-Agent', '')[:255]
                conn2 = get_db()
                with conn2.cursor() as cur:
                    cur.execute(
                        'INSERT INTO login_history (user_id, ip_address, user_agent, status) '
                        'VALUES (%s, %s, %s, %s)',
                        (user['id'], ip, ua, 'failed'))
                conn2.commit()
                conn2.close()
            except Exception:
                pass
        return jsonify(error='Invalid credentials. Check your email/username and password.'), 401

    # ── Per-account lockout check ─────────────────────────────────────────────
    try:
        _check_account_rate_limit(user['id'])
    except _RateLimitError as e:
        return jsonify(error=e.message), 429

    # ── Successful login ──────────────────────────────────────────────────────
    _clear_login_attempts(ip)
    _clear_account_login_attempts(user['id'])

    # Session fixation protection — regenerate session on login
    session.clear()
    session.permanent = True
    session['user_id'] = user['id']
    session['last_active'] = time.time()

    # Record login history and session
    ua = request.headers.get('User-Agent', '')[:255]
    session_id = secrets.token_hex(32)
    session['session_id'] = session_id
    try:
        conn2 = get_db()
        with conn2.cursor() as cur:
            # Log successful login
            cur.execute(
                'INSERT INTO login_history (user_id, ip_address, user_agent, status) '
                'VALUES (%s, %s, %s, %s)',
                (user['id'], ip, ua, 'success'))
            # Track active session
            cur.execute(
                'INSERT INTO user_sessions (user_id, session_id, ip_address, user_agent) '
                'VALUES (%s, %s, %s, %s) '
                'ON DUPLICATE KEY UPDATE last_active=NOW(), ip_address=%s',
                (user['id'], session_id, ip, ua, ip))
            # Keep only last 20 login history records per user
            cur.execute(
                'DELETE FROM login_history WHERE user_id=%s AND id NOT IN ('
                '  SELECT id FROM (SELECT id FROM login_history WHERE user_id=%s '
                '  ORDER BY created_at DESC LIMIT 20) t)',
                (user['id'], user['id']))
        conn2.commit()
        conn2.close()
    except Exception:
        pass  # non-critical — don't fail login if history insert fails

    # Send alert email if admin logs in
    if user.get('is_admin'):
        send_alert_email(
            f'Admin login — IP {ip}',
            f'Admin account "{user["username"]}" logged in successfully.\n\n'
            f'IP address: {ip}\n'
            f'Time: {time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())}\n\n'
            f'If this was not you, change your password and PIN immediately.'
        )

    return jsonify(user=user_dict(user))

@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    # Clear session completely — prevents session fixation
    session.clear()
    response = jsonify(message='Logged out')
    # Expire the session cookie immediately on the client
    response.delete_cookie(app.session_cookie_name)
    # Prevent the browser from caching the logout response
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    return response

@app.route('/api/auth/me')
def auth_me():
    u = current_user()
    if not u:
        return jsonify(error='Not authenticated'), 401
    # Return safe user dict — no password hash, no internal flags
    return jsonify(user=user_dict(u))


# ── Tracks API ────────────────────────────────────────────────────────────────
@app.route('/api/tracks/list')
def tracks_list():
    genre  = request.args.get('genre', '')
    sort   = request.args.get('sort', 'newest')
    mood   = request.args.get('mood', '')
    region = request.args.get('region', '')
    try:
        limit  = min(int(request.args.get('limit', 20)), 100)
        offset = max(int(request.args.get('offset', 0)), 0)
    except (ValueError, TypeError):
        limit, offset = 20, 0
    order  = {
        'newest':    't.created_at DESC',
        'popular':   't.plays DESC',
        'trending':  't.chart_score DESC',
        'downloads': 't.downloads DESC',
        'az':        't.title ASC',
    }.get(sort, 't.created_at DESC')
    where  = ["t.status='published'"]
    params = []
    if genre and genre != 'all':
        where.append('t.genre=%s'); params.append(genre)
    if mood:
        where.append('t.mood=%s'); params.append(mood)
    if region:
        where.append('t.region=%s'); params.append(region)
    where_sql = ' AND '.join(where)
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT t.*, t.likes_count AS likes FROM tracks t "
                "WHERE " + where_sql + " ORDER BY " + order + " LIMIT %s OFFSET %s",
                params + [limit, offset])
            rows = cur.fetchall()
            cur.execute("SELECT COUNT(*) AS c FROM tracks t WHERE " + where_sql, params)
            total = cur.fetchone()['c']
            uid = session.get('user_id')
            liked_ids = set()
            if uid:
                cur.execute('SELECT track_id FROM likes WHERE user_id=%s', (uid,))
                liked_ids = {r['track_id'] for r in cur.fetchall()}
    finally:
        conn.close()
    return jsonify(tracks=[track_dict(r, r['id'] in liked_ids) for r in rows], total=total)


@app.route('/api/tracks/trending')
def tracks_trending():
    limit = min(int(request.args.get('limit', 10)), 50)
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT t.*, t.likes_count AS likes FROM tracks t "
                "WHERE t.status='published' ORDER BY chart_score DESC, plays DESC LIMIT %s",
                (limit,))
            rows = cur.fetchall()
    finally:
        conn.close()
    return jsonify(tracks=[track_dict(r) for r in rows])


@app.route('/api/tracks/charts')
def tracks_charts():
    period = request.args.get('period', 'weekly')
    limit  = min(int(request.args.get('limit', 20)), 50)
    days   = {'daily': 1, 'weekly': 7, 'monthly': 30}.get(period, 7)
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT t.*, t.likes_count AS likes, COUNT(ph.id) AS recent_plays "
                "FROM tracks t "
                "LEFT JOIN play_history ph ON ph.track_id=t.id "
                "  AND ph.played_at >= DATE_SUB(NOW(), INTERVAL %s DAY) "
                "WHERE t.status='published' "
                "GROUP BY t.id "
                "ORDER BY recent_plays DESC, t.chart_score DESC "
                "LIMIT %s",
                (days, limit))
            rows = cur.fetchall()
    finally:
        conn.close()
    return jsonify(tracks=[track_dict(r) for r in rows], period=period)


@app.route('/api/tracks/rising')
def tracks_rising():
    limit = min(int(request.args.get('limit', 10)), 30)
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT t.*, t.likes_count AS likes FROM tracks t "
                "WHERE t.status='published' "
                "AND t.created_at >= DATE_SUB(NOW(), INTERVAL 14 DAY) "
                "ORDER BY t.chart_score DESC LIMIT %s",
                (limit,))
            rows = cur.fetchall()
    finally:
        conn.close()
    return jsonify(tracks=[track_dict(r) for r in rows])


@app.route('/api/tracks/search')
def tracks_search():
    q     = request.args.get('q', '').strip()
    limit = min(int(request.args.get('limit', 20)), 100)
    if not q:
        return jsonify(tracks=[], artists=[], total=0)
    like = '%' + q + '%'
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT t.*, t.likes_count AS likes FROM tracks t "
                "WHERE t.status='published' AND "
                "(t.title LIKE %s OR t.artist_name LIKE %s OR t.genre LIKE %s "
                " OR t.tags LIKE %s OR t.mood LIKE %s OR t.region LIKE %s) "
                "ORDER BY chart_score DESC LIMIT %s",
                (like, like, like, like, like, like, limit))
            tracks = cur.fetchall()
            cur.execute(
                "SELECT u.id, u.display_name, u.avatar_url, u.is_verified, "
                "COUNT(t.id) AS track_count, COALESCE(SUM(t.plays),0) AS total_plays "
                "FROM users u LEFT JOIN tracks t ON t.user_id=u.id AND t.status='published' "
                "WHERE u.display_name LIKE %s OR u.username LIKE %s "
                "GROUP BY u.id ORDER BY total_plays DESC LIMIT 8",
                (like, like))
            artists = cur.fetchall()
    finally:
        conn.close()
    return jsonify(
        tracks=[track_dict(r) for r in tracks],
        artists=[{
            'id': a['id'], 'display_name': a['display_name'],
            'avatar_url': a['avatar_url'], 'is_verified': bool(a['is_verified']),
            'track_count': a['track_count'], 'total_plays': a['total_plays'],
        } for a in artists],
        total=len(tracks))


@app.route('/api/tracks/artists')
def tracks_artists():
    """Return top artists by total plays — used on the homepage."""
    limit = min(int(request.args.get('limit', 8)), 50)
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT u.id, u.display_name, u.avatar_url, u.is_verified, "
                "COUNT(t.id) AS track_count, COALESCE(SUM(t.plays),0) AS total_plays "
                "FROM users u "
                "JOIN tracks t ON t.user_id=u.id AND t.status='published' "
                "WHERE u.role='artist' AND u.is_active=1 "
                "GROUP BY u.id "
                "ORDER BY total_plays DESC LIMIT %s",
                (limit,))
            artists = cur.fetchall()
    finally:
        conn.close()
    return jsonify(artists=[{
        'id': a['id'], 'display_name': a['display_name'],
        'avatar_url': a['avatar_url'], 'is_verified': bool(a['is_verified']),
        'track_count': a['track_count'], 'total_plays': int(a['total_plays']),
    } for a in artists])


@app.route('/api/tracks/<int:track_id>')
def track_get(track_id):
    uid = session.get('user_id')
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT t.*, t.likes_count AS likes FROM tracks t "
                "WHERE t.id=%s AND t.status='published'", (track_id,))
            row = cur.fetchone()
            if not row:
                return jsonify(error='Track not found'), 404
            liked = False
            if uid:
                cur.execute('SELECT 1 FROM likes WHERE user_id=%s AND track_id=%s', (uid, track_id))
                liked = bool(cur.fetchone())
    finally:
        conn.close()
    return jsonify(track=track_dict(row, liked))


@app.route('/api/tracks/play/<int:track_id>', methods=['POST'])
def track_play(track_id):
    uid     = session.get('user_id')
    ip      = _get_client_ip()

    # Fix 8: Rate limit play counts — max 1 play per track per IP per 10 minutes
    # Uses a simple in-memory cache keyed by (ip, track_id)
    import time as _time
    _play_cache_key = f'play:{ip}:{track_id}'
    _now = _time.time()
    if not hasattr(track_play, '_cache'):
        track_play._cache = {}
    last_play = track_play._cache.get(_play_cache_key, 0)
    if _now - last_play < 600:  # 10 minutes
        return jsonify(ok=True)  # silently ignore duplicate plays
    track_play._cache[_play_cache_key] = _now
    # Prune old entries every ~1000 calls to prevent memory growth
    if len(track_play._cache) > 10000:
        cutoff = _now - 600
        track_play._cache = {k: v for k, v in track_play._cache.items() if v > cutoff}

    # Validate country — whitelist to prevent junk data in analytics
    country = (request.form.get('country') or 'Unknown').strip()
    country = country[:60]  # enforce max length
    # Only allow letters, spaces, hyphens — strip anything else
    country = ''.join(c for c in country if c.isalpha() or c in (' ', '-')) or 'Unknown'
    conn = get_db()
    try:
        with conn.cursor() as cur:
            # Verify track exists before incrementing
            cur.execute("SELECT id FROM tracks WHERE id=%s AND status='published'", (track_id,))
            if not cur.fetchone():
                return jsonify(error='Track not found'), 404
            cur.execute('UPDATE tracks SET plays=plays+1 WHERE id=%s', (track_id,))
            cur.execute(
                'INSERT INTO play_history (track_id, user_id, country) VALUES (%s,%s,%s)',
                (track_id, uid, country))
            recalc_chart_score(cur, track_id)
        conn.commit()
    finally:
        conn.close()
    return jsonify(ok=True)


@app.route('/api/tracks/like/<int:track_id>', methods=['POST'])
@login_required
def track_like(track_id):
    uid = session['user_id']
    conn = get_db()
    try:
        with conn.cursor() as cur:
            # Verify track exists and is published
            cur.execute("SELECT id FROM tracks WHERE id=%s AND status='published'", (track_id,))
            if not cur.fetchone():
                return jsonify(error='Track not found'), 404
            cur.execute('SELECT 1 FROM likes WHERE user_id=%s AND track_id=%s', (uid, track_id))
            if cur.fetchone():
                cur.execute('DELETE FROM likes WHERE user_id=%s AND track_id=%s', (uid, track_id))
                cur.execute('UPDATE tracks SET likes_count=GREATEST(0,likes_count-1) WHERE id=%s', (track_id,))
                liked = False
            else:
                cur.execute('INSERT IGNORE INTO likes (user_id,track_id) VALUES (%s,%s)', (uid, track_id))
                cur.execute('UPDATE tracks SET likes_count=likes_count+1 WHERE id=%s', (track_id,))
                liked = True
            recalc_chart_score(cur, track_id)
            conn.commit()
            cur.execute('SELECT likes_count FROM tracks WHERE id=%s', (track_id,))
            count = cur.fetchone()['likes_count']
    finally:
        conn.close()
    return jsonify(liked=liked, likes=count)


@app.route('/api/tracks/share/<int:track_id>', methods=['POST'])
def track_share(track_id):
    # Fix 9: Sharing is public — no login required
    conn = get_db()
    try:
        with conn.cursor() as cur:
            # Verify track exists before incrementing shares
            cur.execute("SELECT id FROM tracks WHERE id=%s AND status='published'", (track_id,))
            if not cur.fetchone():
                return jsonify(error='Track not found'), 404
            cur.execute('UPDATE tracks SET shares=shares+1 WHERE id=%s', (track_id,))
            recalc_chart_score(cur, track_id)
        conn.commit()
    finally:
        conn.close()
    return jsonify(ok=True)


@app.route('/api/tracks/download/<int:track_id>')
def track_download(track_id):
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM tracks WHERE id=%s AND status='published' AND is_free_dl=1",
                (track_id,))
            row = cur.fetchone()
            if not row:
                return jsonify(error='Not available for download'), 403
            cur.execute('UPDATE tracks SET downloads=downloads+1 WHERE id=%s', (track_id,))
            recalc_chart_score(cur, track_id)
        conn.commit()
    finally:
        conn.close()
    # ── Path traversal protection ─────────────────────────────────────────────
    # Use only the basename — never trust the full path stored in DB
    raw_filename = row['audio_url'] or ''
    filename = os.path.basename(raw_filename)
    if not filename or '..' in filename or filename.startswith('/'):
        return jsonify(error='File not available'), 404
    # Sanitize download name — strip any characters that could cause issues
    safe_artist = secure_filename(row['artist_name'])
    safe_title  = secure_filename(row['title'])
    dl_name = f"{safe_artist} - {safe_title}.mp3"
    return send_from_directory(UPLOAD_AUDIO, filename, as_attachment=True, download_name=dl_name)


@app.route('/api/tracks/upload', methods=['POST'])
@login_required
def track_upload():
    uid = session['user_id']
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM users WHERE id=%s AND is_active=1', (uid,))
            u = cur.fetchone()
    finally:
        conn.close()
    if not u:
        return jsonify(error='User not found'), 404

    # ── Email verification check ──────────────────────────────────────────────
    if not u.get('email_verified') and not u.get('is_admin'):
        return jsonify(
            error='Please verify your email address before uploading. '
                  'Check your inbox or request a new verification email.',
            email_unverified=True
        ), 403

    # ── Server-side payment enforcement ──────────────────────────────────────
    # Admins bypass payment. All other artists must have a valid paid plan.
    if not u.get('is_admin'):
        conn_check = get_db()
        try:
            with conn_check.cursor() as cur:
                cur.execute(
                    "SELECT plan, plan_expires_at FROM payments "
                    "WHERE user_id=%s AND status='paid' "
                    "ORDER BY created_at DESC LIMIT 1",
                    (u['id'],))
                paid = cur.fetchone()
        finally:
            conn_check.close()
        if not paid:
            return jsonify(
                error='Upload access requires a completed payment. '
                      'Please purchase an upload plan first.',
                payment_required=True
            ), 402
        # Check plan expiry for monthly/annual
        from datetime import datetime
        now = datetime.utcnow()
        expires_at = paid.get('plan_expires_at')
        if expires_at and expires_at < now:
            return jsonify(
                error='Your upload plan has expired. Please renew to continue uploading.',
                payment_required=True
            ), 402
        # Single plan: only 1 upload allowed
        if paid['plan'] == 'single':
            conn_check2 = get_db()
            try:
                with conn_check2.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) AS c FROM tracks WHERE user_id=%s AND status='published'",
                        (u['id'],))
                    upload_count = cur.fetchone()['c']
            finally:
                conn_check2.close()
            if upload_count >= 1:
                return jsonify(
                    error='Your Single Track plan allows 1 upload. '
                          'Upgrade to Monthly or Annual to upload more.',
                    payment_required=True
                ), 402
    title       = limit((request.form.get('track-title-input') or request.form.get('title') or '').strip(), 'title')
    artist_name = limit((request.form.get('artist-name') or request.form.get('artist_name') or u['display_name']).strip(), 'artist_name')
    genre       = limit((request.form.get('genre-select') or request.form.get('genre') or '').strip(), 'genre')
    mood        = limit((request.form.get('mood') or '').strip(), 'mood')
    region      = limit((request.form.get('region') or 'Zambia').strip(), 'region')
    album       = limit((request.form.get('album-name') or request.form.get('album') or '').strip(), 'album')
    description = limit((request.form.get('track-desc') or request.form.get('description') or '').strip(), 'description')
    tags        = limit((request.form.get('tags-input') or request.form.get('tags') or '').strip(), 'tags')
    if not title or not genre:
        return jsonify(error='Title and genre are required'), 400
    audio_file = request.files.get('audio-file') or request.files.get('audio')
    cover_file = request.files.get('cover-file') or request.files.get('cover')
    if not audio_file or not allowed_file(audio_file.filename, ALLOWED_AUDIO):
        return jsonify(error='Valid audio file required (mp3/wav/flac/aac/ogg)'), 400
    # MIME type validation — check actual file bytes, not just extension
    if not validate_audio_mime(audio_file):
        return jsonify(error='Invalid audio file. File content does not match a supported audio format.'), 400

    # Validate cover if provided
    if cover_file and cover_file.filename:
        if not allowed_file(cover_file.filename, ALLOWED_IMG):
            cover_file = None  # ignore invalid cover, don't block upload
        elif not validate_image_mime(cover_file):
            return jsonify(error='Invalid image file. Only JPG, PNG, GIF, and WebP are allowed.'), 400

    ts         = int(time.time())
    audio_name = str(ts) + '_' + secure_filename(audio_file.filename)
    cover_name = None
    if cover_file and cover_file.filename:
        cover_name = str(ts) + '_' + secure_filename(cover_file.filename)

    # Fix 9: Insert DB record FIRST — only save files if DB succeeds.
    # This prevents orphaned files on disk when the DB insert fails.
    audio_url = '/uploads/audio/' + audio_name
    cover_url = ('/uploads/covers/' + cover_name) if cover_name else None

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'INSERT INTO tracks '
                '(user_id,title,artist_name,genre,mood,region,album,description,tags,audio_url,cover_url) '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (u['id'], title, artist_name, genre, mood, region,
                 album, description, tags, audio_url, cover_url))
            conn.commit()
            new_track_id = cur.lastrowid
            cur.execute('SELECT * FROM tracks WHERE id=%s', (new_track_id,))
            track = cur.fetchone()
    except Exception as e:
        app.logger.error('Track DB insert failed: %s', e)
        return jsonify(error='Upload failed. Please try again.'), 500
    finally:
        conn.close()

    # DB succeeded — now save the files to disk
    try:
        audio_file.save(os.path.join(UPLOAD_AUDIO, audio_name))
        if cover_file and cover_name:
            cover_file.save(os.path.join(UPLOAD_COVER, cover_name))
    except Exception as e:        # File save failed — clean up the DB record to keep things consistent
        app.logger.error('File save failed after DB insert (track %s): %s', new_track_id, e)
        try:
            conn2 = get_db()
            with conn2.cursor() as cur:
                cur.execute('DELETE FROM tracks WHERE id=%s', (new_track_id,))
            conn2.commit()
            conn2.close()
        except Exception:
            pass
        return jsonify(error='File could not be saved. Please try again.'), 500

    # Detect audio duration using mutagen and update the track record
    try:
        audio_path = os.path.join(UPLOAD_AUDIO, audio_name)
        meta = MutagenFile(audio_path)
        duration = int(meta.info.length) if meta and hasattr(meta, 'info') else 0
        if duration > 0:
            conn3 = get_db()
            try:
                with conn3.cursor() as cur:
                    cur.execute('UPDATE tracks SET duration=%s WHERE id=%s', (duration, new_track_id))
                    cur.execute('SELECT * FROM tracks WHERE id=%s', (new_track_id,))
                    track = cur.fetchone()
                conn3.commit()
            finally:
                conn3.close()
    except Exception as e:
        app.logger.warning('Could not detect duration for track %s: %s', new_track_id, e)
        # Non-critical — upload still succeeds, duration stays 0

    return jsonify(message='Track uploaded successfully!', track=track_dict(track)), 201


@app.route('/api/tracks/<int:track_id>', methods=['DELETE'])
@login_required
def track_delete(track_id):
    uid = session['user_id']
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM users WHERE id=%s AND is_active=1', (uid,))
            u = cur.fetchone()
            cur.execute('SELECT * FROM tracks WHERE id=%s', (track_id,))
            row = cur.fetchone()
            if not row:
                return jsonify(error='Track not found'), 404
            if row['user_id'] != uid and not u.get('is_admin'):
                return jsonify(error='Forbidden'), 403
            cur.execute('DELETE FROM tracks WHERE id=%s', (track_id,))
        conn.commit()
    finally:
        conn.close()
    # Clean up audio and cover files after successful DB delete
    for url in (row.get('audio_url') or '', row.get('cover_url') or ''):
        if not url:
            continue
        fname = os.path.basename(url)
        if not fname or '..' in fname:
            continue
        folder = UPLOAD_AUDIO if '/audio/' in url else UPLOAD_COVER
        fpath  = os.path.join(folder, fname)
        try:
            if os.path.isfile(fpath):
                os.remove(fpath)
        except Exception as e:
            app.logger.warning('Could not delete file %s: %s', fpath, e)
    return jsonify(message='Track deleted')


@app.route('/api/tracks/comments')
def track_comments():
    track_id = request.args.get('id') or request.args.get('track_id')
    if not track_id:
        return jsonify(comments=[])
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT c.*, u.display_name, u.avatar_url, u.is_verified "
                "FROM comments c JOIN users u ON u.id=c.user_id "
                "WHERE c.track_id=%s ORDER BY c.created_at DESC LIMIT 50",
                (track_id,))
            rows = cur.fetchall()
    finally:
        conn.close()
    return jsonify(comments=[{
        'id': r['id'], 'body': r['body'], 'likes': r['likes'],
        'display_name': r['display_name'], 'avatar_url': r['avatar_url'],
        'is_verified': bool(r['is_verified']),
        'created_at': str(r['created_at'])} for r in rows])


@app.route('/api/tracks/comment', methods=['POST'])
@login_required
def track_comment():
    uid = session['user_id']
    try:
        track_id = int(request.form.get('track_id') or request.form.get('id') or 0)
    except (ValueError, TypeError):
        return jsonify(error='Invalid track ID'), 400
    body = limit((request.form.get('body') or '').strip(), 'comment_body')
    if not track_id or not body:
        return jsonify(error='Track ID and comment body required'), 400
    if len(body) > INPUT_LIMITS['comment_body']:
        return jsonify(error=f'Comment must be {INPUT_LIMITS["comment_body"]} characters or less'), 400
    conn = get_db()
    try:
        with conn.cursor() as cur:
            # Verify track exists and is published
            cur.execute("SELECT id FROM tracks WHERE id=%s AND status='published'", (track_id,))
            if not cur.fetchone():
                return jsonify(error='Track not found'), 404
            cur.execute('INSERT INTO comments (track_id,user_id,body) VALUES (%s,%s,%s)',
                        (track_id, uid, body))
        conn.commit()
    finally:
        conn.close()
    return jsonify(message='Comment posted')


VALID_REPORT_REASONS = {
    'copyright_infringement', 'inappropriate_content',
    'spam', 'fake_impersonation', 'other'
}

@app.route('/api/tracks/report', methods=['POST'])
@login_required
def track_report():
    uid = session['user_id']
    try:
        track_id = int(request.form.get('track_id') or 0)
    except (ValueError, TypeError):
        return jsonify(error='Invalid track ID'), 400
    reason  = (request.form.get('reason') or '').strip().lower()
    details = limit((request.form.get('details') or '').strip(), 'description')
    if not track_id or not reason:
        return jsonify(error='Track ID and reason required'), 400
    # Validate reason against whitelist
    if reason not in VALID_REPORT_REASONS:
        return jsonify(error=f'Invalid reason. Must be one of: {", ".join(VALID_REPORT_REASONS)}'), 400
    conn = get_db()
    try:
        with conn.cursor() as cur:
            # Verify track exists
            cur.execute("SELECT id FROM tracks WHERE id=%s", (track_id,))
            if not cur.fetchone():
                return jsonify(error='Track not found'), 404
            # Prevent duplicate reports from same user on same track
            cur.execute(
                "SELECT id FROM reports WHERE reporter_id=%s AND track_id=%s AND status='pending'",
                (uid, track_id))
            if cur.fetchone():
                return jsonify(message='You have already reported this track.'), 200
            cur.execute(
                'INSERT INTO reports (reporter_id,track_id,reason,details) VALUES (%s,%s,%s,%s)',
                (uid, track_id, reason, details))
        conn.commit()
    finally:
        conn.close()
    return jsonify(message='Report submitted. Our team will review it within 48 hours.')



# ── User API ──────────────────────────────────────────────────────────────────
@app.route('/api/user/profile')
@login_required
def user_profile():
    uid = session['user_id']
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM users WHERE id=%s AND is_active=1', (uid,))
            u = cur.fetchone()
            if not u:
                return jsonify(error='User not found'), 404
            cur.execute(
                "SELECT COUNT(*) AS track_count, COALESCE(SUM(plays),0) AS total_plays, "
                "COALESCE(SUM(downloads),0) AS total_downloads, "
                "COALESCE(SUM(likes_count),0) AS total_likes "
                "FROM tracks WHERE user_id=%s AND status='published'",
                (uid,))
            stats = cur.fetchone()
            likes_total = int(stats['total_likes'] or 0)
            cur.execute('SELECT COUNT(*) AS c FROM follows WHERE target_id=%s', (uid,))
            followers = cur.fetchone()['c']
    finally:
        conn.close()
    profile = dict(user_dict(u))
    # Fix 9: Include email so the settings tab can display it (read-only)
    profile['email'] = u.get('email', '')
    profile.update({
        'track_count':     stats['track_count'],
        'total_plays':     stats['total_plays'],
        'total_downloads': stats['total_downloads'],
        'total_likes':     likes_total,
        'followers':       followers,
    })
    return jsonify(profile=profile)


@app.route('/api/user/analytics')
@login_required
def user_analytics():
    uid = session['user_id']
    conn = get_db()
    try:
        with conn.cursor() as cur:
            # Top tracks by downloads
            cur.execute(
                "SELECT id, title, artist_name, plays, downloads, likes_count, chart_score "
                "FROM tracks WHERE user_id=%s AND status='published' "
                "ORDER BY downloads DESC LIMIT 10",
                (uid,))
            top_tracks = cur.fetchall()
            # Daily plays last 30 days
            cur.execute(
                "SELECT DATE(played_at) AS day, COUNT(*) AS plays "
                "FROM play_history ph JOIN tracks t ON t.id=ph.track_id "
                "WHERE t.user_id=%s AND ph.played_at >= DATE_SUB(NOW(), INTERVAL 30 DAY) "
                "GROUP BY day ORDER BY day",
                (uid,))
            daily_plays = cur.fetchall()
            # Top countries
            cur.execute(
                "SELECT ph.country, COUNT(*) AS plays "
                "FROM play_history ph JOIN tracks t ON t.id=ph.track_id "
                "WHERE t.user_id=%s "
                "GROUP BY ph.country ORDER BY plays DESC LIMIT 10",
                (uid,))
            countries = cur.fetchall()
    finally:
        conn.close()
    return jsonify(
        top_tracks=[{
            'id': t['id'], 'title': t['title'], 'artist_name': t['artist_name'],
            'plays': t['plays'], 'downloads': t['downloads'],
            'likes': t['likes_count'], 'chart_score': float(t['chart_score']),
        } for t in top_tracks],
        daily_plays=[{'day': str(r['day']), 'plays': r['plays']} for r in daily_plays],
        countries=[{'country': r['country'], 'plays': r['plays']} for r in countries],
    )


@app.route('/api/user/tracks')
@login_required
def user_tracks():
    uid = session['user_id']
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT t.*, t.likes_count AS likes FROM tracks t "
                "WHERE t.user_id=%s ORDER BY created_at DESC",
                (uid,))
            rows = cur.fetchall()
    finally:
        conn.close()
    return jsonify(tracks=[track_dict(r) for r in rows])


@app.route('/api/user/favorites')
@login_required
def user_favorites():
    uid = session['user_id']
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT t.*, t.likes_count AS likes FROM tracks t "
                "JOIN likes l ON l.track_id=t.id "
                "WHERE l.user_id=%s AND t.status='published' ORDER BY t.plays DESC",
                (uid,))
            rows = cur.fetchall()
    finally:
        conn.close()
    return jsonify(tracks=[track_dict(r, True) for r in rows])


@app.route('/api/user/playlists')
@login_required
def user_playlists():
    uid = session['user_id']
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT p.*, COUNT(pt.track_id) AS track_count FROM playlists p '
                'LEFT JOIN playlist_tracks pt ON pt.playlist_id=p.id '
                'WHERE p.user_id=%s GROUP BY p.id ORDER BY p.created_at DESC',
                (uid,))
            rows = cur.fetchall()
    finally:
        conn.close()
    return jsonify(playlists=[{
        'id': r['id'], 'name': r['name'], 'description': r['description'],
        'is_public': bool(r['is_public']), 'track_count': r['track_count'],
        'covers': []} for r in rows])


@app.route('/api/user/playlists', methods=['POST'])
@login_required
def user_playlist_create():
    uid   = session['user_id']
    name  = (request.form.get('name') or '').strip()
    desc  = (request.form.get('description') or '').strip()
    pub   = request.form.get('is_public', '1') == '1'
    if not name:
        return jsonify(error='Playlist name is required'), 400
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'INSERT INTO playlists (user_id, name, description, is_public) '
                'VALUES (%s,%s,%s,%s)',
                (uid, name, desc, int(pub)))
            conn.commit()
            new_id = cur.lastrowid
    finally:
        conn.close()
    return jsonify(message='Playlist created!', id=new_id, name=name), 201


@app.route('/api/user/playlists/<int:playlist_id>/tracks', methods=['POST'])
@login_required
def user_playlist_add_track():
    uid      = session['user_id']
    track_id = request.form.get('track_id')
    if not track_id:
        return jsonify(error='track_id required'), 400
    conn = get_db()
    try:
        with conn.cursor() as cur:
            # Verify playlist belongs to user
            cur.execute('SELECT id FROM playlists WHERE id=%s AND user_id=%s',
                        (playlist_id, uid))
            if not cur.fetchone():
                return jsonify(error='Playlist not found'), 404
            cur.execute(
                'INSERT IGNORE INTO playlist_tracks (playlist_id, track_id) VALUES (%s,%s)',
                (playlist_id, track_id))
        conn.commit()
    finally:
        conn.close()
    return jsonify(message='Track added to playlist')


@app.route('/api/user/update_avatar', methods=['POST'])
@login_required
def user_update_avatar():
    """Upload and update the user's profile avatar."""
    uid = session['user_id']
    avatar_file = request.files.get('avatar')
    if not avatar_file or not avatar_file.filename:
        return jsonify(error='No image file provided'), 400
    if not allowed_file(avatar_file.filename, ALLOWED_IMG):
        return jsonify(error='Only JPG, PNG, WebP or GIF images are allowed'), 400
    if not validate_image_mime(avatar_file):
        return jsonify(error='Invalid image file. File content does not match a supported format.'), 400
    # Check file size (max 10MB)
    avatar_file.seek(0, 2)
    size = avatar_file.tell()
    avatar_file.seek(0)
    if size > MAX_IMG_MB * 1024 * 1024:
        return jsonify(error=f'Image must be under {MAX_IMG_MB}MB'), 400

    ts          = int(time.time())
    avatar_name = f'{uid}_{ts}_' + secure_filename(avatar_file.filename)
    avatar_path = os.path.join(UPLOAD_AVATAR, avatar_name)
    avatar_url  = '/uploads/avatars/' + avatar_name

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT avatar_url FROM users WHERE id=%s', (uid,))
            old = cur.fetchone()
            cur.execute('UPDATE users SET avatar_url=%s WHERE id=%s', (avatar_url, uid))
        conn.commit()
    except Exception as e:
        app.logger.error('Avatar DB update failed: %s', e)
        return jsonify(error='Could not update avatar. Please try again.'), 500
    finally:
        conn.close()

    # Save file after DB succeeds
    try:
        avatar_file.save(avatar_path)
    except Exception as e:
        app.logger.error('Avatar file save failed: %s', e)
        return jsonify(error='File could not be saved. Please try again.'), 500

    # Delete old avatar file if it exists
    if old and old.get('avatar_url'):
        old_fname = os.path.basename(old['avatar_url'])
        if old_fname and '..' not in old_fname:
            old_path = os.path.join(UPLOAD_AVATAR, old_fname)
            try:
                if os.path.isfile(old_path):
                    os.remove(old_path)
            except Exception:
                pass

    return jsonify(avatar_url=avatar_url, message='Profile photo updated!')


@app.route('/api/user/update', methods=['POST'])
@login_required
def user_update():
    uid  = session['user_id']
    d    = request.form
    name = limit((d.get('display_name') or '').strip(), 'display_name')
    bio  = limit((d.get('bio') or '').strip(), 'bio')
    web  = limit((d.get('website') or '').strip(), 'website')
    # Fix 8: Validate display_name explicitly — don't silently keep old value
    if not name:
        return jsonify(error='Display name cannot be empty'), 400
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'UPDATE users SET display_name=%s, bio=%s, website=%s WHERE id=%s',
                (name, bio, web, uid))
            conn.commit()
            cur.execute('SELECT * FROM users WHERE id=%s', (uid,))
            user = cur.fetchone()
    finally:
        conn.close()
    return jsonify(user=user_dict(user))


@app.route('/api/user/follow', methods=['POST'])
@login_required
def user_follow():
    uid = session['user_id']
    try:
        target_id = int(request.form.get('target_id', 0))
    except (ValueError, TypeError):
        return jsonify(error='Invalid target'), 400
    if not target_id or target_id == uid:
        return jsonify(error='Invalid target'), 400
    conn = get_db()
    try:
        with conn.cursor() as cur:
            # Fix 8: Verify target user exists before following
            cur.execute('SELECT id FROM users WHERE id=%s AND is_active=1', (target_id,))
            if not cur.fetchone():
                return jsonify(error='User not found'), 404
            cur.execute('SELECT 1 FROM follows WHERE follower_id=%s AND target_id=%s', (uid, target_id))
            if cur.fetchone():
                cur.execute('DELETE FROM follows WHERE follower_id=%s AND target_id=%s', (uid, target_id))
                following = False
            else:
                cur.execute('INSERT IGNORE INTO follows (follower_id,target_id) VALUES (%s,%s)', (uid, target_id))
                following = True
            conn.commit()
    finally:
        conn.close()
    return jsonify(following=following)


# ── Payment API (ZMW) ─────────────────────────────────────────────────────────
@app.route('/api/payment/plans')
def payment_plans():
    return jsonify(plans=PLAN_PRICES)


@app.route('/api/payment/initiate', methods=['POST'])
@login_required
def payment_initiate():
    uid    = session['user_id']
    plan   = (request.form.get('plan') or '').strip()
    method = (request.form.get('method') or 'card').strip()
    if not plan:
        return jsonify(error='Please select a plan before proceeding.'), 400
    if plan not in PLAN_PRICES:
        return jsonify(error='Invalid plan. Choose single, monthly, or annual.'), 400
    amount    = PLAN_PRICES[plan]['zmw']
    reference = secrets.token_hex(16)
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'INSERT INTO payments (user_id,plan,amount_zmw,method,status,reference) '
                'VALUES (%s,%s,%s,%s,%s,%s)',
                (uid, plan, amount, method, 'pending', reference))
            conn.commit()
            new_id = cur.lastrowid
    finally:
        conn.close()
    return jsonify(
        payment_id=new_id, reference=reference,
        amount_zmw=amount, label=PLAN_PRICES[plan]['label'], plan=plan)


@app.route('/api/payment/confirm', methods=['POST'])
@login_required
def payment_confirm():
    uid        = session['user_id']
    payment_id = request.form.get('payment_id')
    reference  = request.form.get('reference')
    if not payment_id or not reference:
        return jsonify(error='payment_id and reference are required'), 400
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT * FROM payments WHERE id=%s AND user_id=%s AND reference=%s',
                (payment_id, uid, reference))
            row = cur.fetchone()
            if not row:
                return jsonify(error='Payment not found'), 404
            # Prevent double-confirmation
            if row['status'] != 'pending':
                return jsonify(error='Payment already processed'), 409
            # Verify amount matches the plan — prevents tampering
            expected_amount = PLAN_PRICES.get(row['plan'], {}).get('zmw')
            if expected_amount is None or float(row['amount_zmw']) != float(expected_amount):
                app.logger.warning(
                    'Payment amount mismatch: user=%s plan=%s expected=%s got=%s',
                    uid, row['plan'], expected_amount, row['amount_zmw'])
                return jsonify(error='Payment amount mismatch. Please contact support.'), 400
            # Calculate plan expiry
            from datetime import datetime
            now = datetime.utcnow()
            if row['plan'] == 'annual':
                from datetime import timedelta
                expires_at = now + timedelta(days=365)
            elif row['plan'] == 'monthly':
                from datetime import timedelta
                expires_at = now + timedelta(days=30)
            else:  # single — no expiry, but track upload count
                expires_at = None
            cur.execute(
                "UPDATE payments SET status='paid', plan_expires_at=%s WHERE id=%s",
                (expires_at, payment_id))
            cur.execute("UPDATE users SET role='artist' WHERE id=%s", (uid,))
            conn.commit()
    finally:
        conn.close()
    return jsonify(message='Payment confirmed. Upload access unlocked!', plan=row['plan'])


@app.route('/api/user/plan_status')
@login_required
def user_plan_status():
    """Return the artist's current active plan and upload stats."""
    uid = session['user_id']
    conn = get_db()
    try:
        with conn.cursor() as cur:
            # Get most recent paid payment
            cur.execute(
                "SELECT plan, amount_zmw, plan_expires_at, created_at "
                "FROM payments WHERE user_id=%s AND status='paid' "
                "ORDER BY created_at DESC LIMIT 1",
                (uid,))
            payment = cur.fetchone()
            # Count uploads this month (for single-plan enforcement)
            cur.execute(
                "SELECT COUNT(*) AS c FROM tracks "
                "WHERE user_id=%s AND status='published' "
                "AND created_at >= DATE_FORMAT(NOW(), '%%Y-%%m-01')",
                (uid,))
            uploads_this_month = cur.fetchone()['c']
            cur.execute(
                "SELECT COUNT(*) AS c FROM tracks WHERE user_id=%s AND status='published'",
                (uid,))
            total_uploads = cur.fetchone()['c']
    finally:
        conn.close()

    if not payment:
        return jsonify(plan=None, active=False,
                       message='No active plan. Purchase a plan to upload music.')

    from datetime import datetime
    now = datetime.utcnow()
    expires_at = payment.get('plan_expires_at')
    plan = payment['plan']

    # Check expiry for monthly/annual
    if expires_at and expires_at < now:
        return jsonify(plan=plan, active=False,
                       expires_at=str(expires_at),
                       message='Your plan has expired. Please renew to upload.')

    # Single plan: only 1 upload allowed total
    if plan == 'single' and total_uploads >= 1:
        return jsonify(plan=plan, active=False,
                       uploads_used=total_uploads, uploads_allowed=1,
                       message='Single plan allows 1 upload. Upgrade to upload more.')

    return jsonify(
        plan=plan,
        active=True,
        expires_at=str(expires_at) if expires_at else None,
        uploads_this_month=uploads_this_month,
        total_uploads=total_uploads,
        label=PLAN_PRICES.get(plan, {}).get('label', plan),
        message=f'Active: {PLAN_PRICES.get(plan, {}).get("label", plan)} plan'
    )


# ── Contact API ───────────────────────────────────────────────────────────────
@app.route('/api/contact/', methods=['POST'])
def contact_send():
    d       = request.get_json(silent=True) or request.form
    name    = limit((d.get('contact-name') or d.get('name') or '').strip(), 'name')
    email   = limit((d.get('contact-email') or d.get('email') or '').strip(), 'email')
    subject = limit((d.get('contact-subject') or d.get('subject') or '').strip(), 'subject')
    message = limit((d.get('contact-message') or d.get('message') or '').strip(), 'message')
    if not all([name, email, message]):
        return jsonify(error='Name, email and message are required'), 400
    # Basic email format check
    if '@' not in email or '.' not in email.split('@')[-1]:
        return jsonify(error='Please enter a valid email address'), 400
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'INSERT INTO contact_messages (name,email,subject,message) VALUES (%s,%s,%s,%s)',
                (name, email, subject, message))
        conn.commit()
    finally:
        conn.close()

    # ── Notify admin by email (non-blocking) ──────────────────────────────────
    admin_to = ALERT_EMAIL_TO or os.environ.get('ADMIN_EMAIL', '')
    if admin_to:
        body_text = (
            f"New contact message on SMADS African Hits\n\n"
            f"From:    {name} <{email}>\n"
            f"Subject: {subject or '(no subject)'}\n\n"
            f"Message:\n{message}\n\n"
            f"---\nReply directly to {email}"
        )
        body_html = (
            f"<h2>New Contact Message</h2>"
            f"<p><strong>From:</strong> {name} &lt;{email}&gt;</p>"
            f"<p><strong>Subject:</strong> {subject or '(no subject)'}</p>"
            f"<hr><p style='white-space:pre-wrap'>{message}</p>"
            f"<hr><p>Reply directly to <a href='mailto:{email}'>{email}</a></p>"
        )
        send_email(
            to=admin_to,
            subject=f"[SMADS Contact] {subject or 'New message from ' + name}",
            body_text=body_text,
            body_html=body_html,
        )

    # ── Auto-reply to sender ──────────────────────────────────────────────────
    send_email(
        to=email,
        subject="We received your message – SMADS African Hits",
        body_text=(
            f"Hi {name},\n\n"
            f"Thanks for reaching out! We've received your message and will get back to you within 24 hours.\n\n"
            f"Your message:\n{message}\n\n"
            f"Best regards,\nThe SMADS African Hits Team"
        ),
        body_html=(
            f"<p>Hi {name},</p>"
            f"<p>Thanks for reaching out! We've received your message and will get back to you within 24 hours.</p>"
            f"<blockquote style='border-left:3px solid #6c63ff;padding-left:1rem;color:#666'>{message}</blockquote>"
            f"<p>Best regards,<br><strong>The SMADS African Hits Team</strong></p>"
        ),
    )

    return jsonify(message="Message received! We'll get back to you within 24 hours.")


# ── Admin API ─────────────────────────────────────────────────────────────────
@app.route('/api/admin/ping')
@admin_required
def admin_ping():
    """Fix 9: Lightweight endpoint to verify admin PIN status without a heavy DB query."""
    return jsonify(ok=True)


@app.route('/api/admin/stats')
def admin_stats():
    # Fix 6: Require admin login for stats — non-admins get zeros only
    u = current_user()
    if not u:
        return jsonify(stats={
            'total_users': 0, 'total_tracks': 0,
            'total_plays': 0, 'total_downloads': 0,
            'total_revenue_zmw': 0, 'total_revenue': 0,
            'pending_reports': 0, 'genres': [], 'recent_activity': []
        })
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) AS c FROM users')
            total_users = cur.fetchone()['c']
            cur.execute("SELECT COUNT(*) AS c FROM tracks WHERE status='published'")
            total_tracks = cur.fetchone()['c']
            cur.execute('SELECT COALESCE(SUM(plays),0) AS c FROM tracks')
            total_plays = cur.fetchone()['c']
            cur.execute('SELECT COALESCE(SUM(downloads),0) AS c FROM tracks')
            total_downloads = cur.fetchone()['c']

            # Admin-only fields
            total_revenue    = 0
            pending_reports  = 0
            genres           = []
            recent           = []
            if u and u['is_admin']:
                cur.execute("SELECT COALESCE(SUM(amount_zmw),0) AS c FROM payments WHERE status='paid'")
                total_revenue = float(cur.fetchone()['c'])
                cur.execute("SELECT COUNT(*) AS c FROM reports WHERE status='pending'")
                pending_reports = cur.fetchone()['c']
                cur.execute(
                    "SELECT genre, SUM(plays) AS plays FROM tracks WHERE status='published' "
                    "GROUP BY genre ORDER BY plays DESC LIMIT 8")
                genres = cur.fetchall()
                cur.execute(
                    "SELECT 'upload' AS type, u.display_name AS user, "
                    "CONCAT(t.title,' (',t.genre,')') AS detail, t.created_at AS time "
                    "FROM tracks t JOIN users u ON u.id=t.user_id "
                    "UNION ALL "
                    "SELECT 'payment', u.display_name, CONCAT(p.plan,' K',p.amount_zmw), p.created_at "
                    "FROM payments p JOIN users u ON u.id=p.user_id WHERE p.status='paid' "
                    "ORDER BY time DESC LIMIT 10")
                recent = cur.fetchall()
    finally:
        conn.close()

    return jsonify(stats={
        'total_users':       total_users,
        'total_tracks':      total_tracks,
        'total_plays':       total_plays,
        'total_downloads':   total_downloads,
        'total_revenue_zmw': round(total_revenue, 2),
        'total_revenue':     round(total_revenue, 2),  # alias for frontend
        'pending_reports':   pending_reports,
        'genres': [{'genre': g['genre'], 'plays': g['plays']} for g in genres],
        'recent_activity': [{'type': r['type'], 'user': r['user'],
                              'detail': r['detail'], 'time': str(r['time'])} for r in recent],
    })


@app.route('/api/admin/users')
@admin_required
def admin_users():
    try:
        limit  = min(int(request.args.get('limit', 20)), 200)
        offset = max(int(request.args.get('offset', 0)), 0)
    except (ValueError, TypeError):
        limit, offset = 20, 0
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT * FROM users ORDER BY created_at DESC LIMIT %s OFFSET %s', (limit, offset))
            rows = cur.fetchall()
            cur.execute('SELECT COUNT(*) AS c FROM users')
            total = cur.fetchone()['c']
    finally:
        conn.close()
    return jsonify(users=[user_dict(u) for u in rows], total=total)


@app.route('/api/admin/tracks')
@admin_required
def admin_tracks():
    try:
        limit  = min(int(request.args.get('limit', 20)), 200)
        offset = max(int(request.args.get('offset', 0)), 0)
    except (ValueError, TypeError):
        limit, offset = 20, 0
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT t.*, t.likes_count AS likes FROM tracks t "
                "ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (limit, offset))
            rows = cur.fetchall()
            cur.execute('SELECT COUNT(*) AS c FROM tracks')
            total = cur.fetchone()['c']
    finally:
        conn.close()
    return jsonify(tracks=[track_dict(r) for r in rows], total=total)


@app.route('/api/admin/payments')
@admin_required
def admin_payments():
    try:
        limit  = min(int(request.args.get('limit', 20)), 200)
        offset = max(int(request.args.get('offset', 0)), 0)
    except (ValueError, TypeError):
        limit, offset = 20, 0
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT p.*, u.display_name FROM payments p JOIN users u ON u.id=p.user_id '
                'ORDER BY p.created_at DESC LIMIT %s OFFSET %s',
                (limit, offset))
            rows = cur.fetchall()
    finally:
        conn.close()
    return jsonify(payments=[{
        'id': r['id'], 'display_name': r['display_name'], 'plan': r['plan'],
        'amount': 'K' + str(float(r['amount_zmw'])),
        'method': r['method'], 'status': r['status'],
        'created_at': str(r['created_at'])} for r in rows])


@app.route('/api/admin/reports')
@admin_required
def admin_reports():
    try:
        limit  = min(int(request.args.get('limit', 20)), 100)
        offset = max(int(request.args.get('offset', 0)), 0)
    except (ValueError, TypeError):
        limit, offset = 20, 0
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT r.*, u.display_name AS reporter_name, t.title AS track_title "
                "FROM reports r "
                "JOIN users u ON u.id=r.reporter_id "
                "LEFT JOIN tracks t ON t.id=r.track_id "
                "ORDER BY r.created_at DESC LIMIT %s OFFSET %s",
                (limit, offset))
            rows = cur.fetchall()
    finally:
        conn.close()
    return jsonify(reports=[{
        'id': r['id'], 'reporter_name': r['reporter_name'],
        'track_title': r['track_title'], 'reason': r['reason'],
        'details': r['details'], 'status': r['status'],
        'created_at': str(r['created_at'])} for r in rows])


@app.route('/api/admin/update_user', methods=['POST'])
@admin_required
def admin_update_user():
    try:
        uid = int(request.form.get('id', 0))
        is_active = int(request.form.get('is_active', '1'))
    except (ValueError, TypeError):
        return jsonify(error='Invalid parameters'), 400
    if not uid:
        return jsonify(error='User ID required'), 400
    if is_active not in (0, 1):
        return jsonify(error='is_active must be 0 or 1'), 400
    # Prevent admin from deactivating their own account
    if uid == session.get('user_id'):
        return jsonify(error='You cannot deactivate your own account'), 400
    conn = get_db()
    try:
        with conn.cursor() as cur:
            # Verify user exists
            cur.execute('SELECT id, is_admin FROM users WHERE id=%s', (uid,))
            target = cur.fetchone()
            if not target:
                return jsonify(error='User not found'), 404
            # Prevent deactivating other admins
            if target['is_admin'] and not is_active:
                return jsonify(error='Cannot deactivate an admin account'), 403
            cur.execute('UPDATE users SET is_active=%s WHERE id=%s', (is_active, uid))
        conn.commit()
    finally:
        conn.close()
    return jsonify(message='User updated')


@app.route('/api/admin/verify_artist', methods=['POST'])
@admin_required
def admin_verify_artist():
    try:
        uid = int(request.form.get('id', 0))
        val = int(request.form.get('is_verified', 1))
    except (ValueError, TypeError):
        return jsonify(error='Invalid parameters'), 400
    if not uid:
        return jsonify(error='User ID required'), 400
    if val not in (0, 1):
        return jsonify(error='is_verified must be 0 or 1'), 400
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT id FROM users WHERE id=%s', (uid,))
            if not cur.fetchone():
                return jsonify(error='User not found'), 404
            cur.execute('UPDATE users SET is_verified=%s WHERE id=%s', (val, uid))
        conn.commit()
    finally:
        conn.close()
    return jsonify(message='Artist verification updated')


@app.route('/api/admin/grant_upload', methods=['POST'])
@admin_required
def admin_grant_upload():
    """Record a manual (cash) payment and ensure the user has artist role."""
    uid        = request.form.get('user_id', '').strip()
    amount_str = request.form.get('amount_zmw', '').strip()
    plan       = request.form.get('plan', 'single').strip()

    if not uid or not amount_str:
        return jsonify(error='User ID and amount are required'), 400
    try:
        amount = float(amount_str)
        if amount <= 0:
            raise ValueError
    except ValueError:
        return jsonify(error='Amount must be a positive number'), 400
    if plan not in ('single', 'monthly', 'annual'):
        plan = 'single'

    reference = 'CASH-' + secrets.token_hex(8).upper()

    # Calculate plan expiry (same logic as payment_confirm)
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    if plan == 'annual':
        expires_at = now + timedelta(days=365)
    elif plan == 'monthly':
        expires_at = now + timedelta(days=30)
    else:
        expires_at = None  # single — no expiry, 1-upload limit enforced elsewhere

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT id, display_name, role FROM users WHERE id=%s', (uid,))
            target = cur.fetchone()
            if not target:
                return jsonify(error='User not found'), 404
            if target['role'] == 'listener':
                cur.execute("UPDATE users SET role='artist' WHERE id=%s", (uid,))
            cur.execute(
                'INSERT INTO payments (user_id, plan, amount_zmw, method, status, reference, plan_expires_at) '
                'VALUES (%s, %s, %s, %s, %s, %s, %s)',
                (uid, plan, amount, 'cash', 'paid', reference, expires_at))
        conn.commit()
    finally:
        conn.close()

    return jsonify(
        message=f"Upload access granted to {target['display_name']}. "
                f"Cash payment of K{amount:.2f} recorded (ref: {reference}).",
        reference=reference
    )


@app.route('/api/admin/delete_track', methods=['DELETE'])
@admin_required
def admin_delete_track():
    try:
        track_id = int(request.args.get('id', 0))
    except (ValueError, TypeError):
        return jsonify(error='Invalid track ID'), 400
    if not track_id:
        return jsonify(error='Track ID required'), 400
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT audio_url, cover_url FROM tracks WHERE id=%s', (track_id,))
            row = cur.fetchone()
            if not row:
                return jsonify(error='Track not found'), 404
            cur.execute('DELETE FROM tracks WHERE id=%s', (track_id,))
        conn.commit()
    finally:
        conn.close()
    # Clean up files
    for url in (row.get('audio_url') or '', row.get('cover_url') or ''):
        if not url:
            continue
        fname = os.path.basename(url)
        if not fname or '..' in fname:
            continue
        folder = UPLOAD_AUDIO if '/audio/' in url else UPLOAD_COVER
        fpath  = os.path.join(folder, fname)
        try:
            if os.path.isfile(fpath):
                os.remove(fpath)
        except Exception as e:
            app.logger.warning('Admin delete: could not remove file %s: %s', fpath, e)
    return jsonify(message='Track removed')


@app.route('/api/admin/resolve_report', methods=['POST'])
@admin_required
def admin_resolve_report():
    # Fix 7: Validate report_id is a valid integer
    try:
        report_id = int(request.form.get('id') or 0)
    except (ValueError, TypeError):
        return jsonify(error='Invalid report ID'), 400
    if not report_id:
        return jsonify(error='Report ID required'), 400
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM reports WHERE id=%s", (report_id,))
            if not cur.fetchone():
                return jsonify(error='Report not found'), 404
            cur.execute("UPDATE reports SET status='resolved' WHERE id=%s", (report_id,))
        conn.commit()
    finally:
        conn.close()
    return jsonify(message='Report resolved')


@app.route('/api/admin/settings', methods=['POST'])
@admin_required
def admin_settings():
    # Fix 7: Actually persist settings to admin_settings table
    d = request.get_json(silent=True) or request.form
    allowed_keys = {'site_name', 'price_single', 'price_monthly', 'price_annual',
                    'allow_free_downloads', 'require_email_verification'}
    conn = get_db()
    try:
        with conn.cursor() as cur:
            for key, value in d.items():
                if key in allowed_keys:
                    cur.execute(
                        "INSERT INTO admin_settings (key_name, value) VALUES (%s, %s) "
                        "ON DUPLICATE KEY UPDATE value=%s",
                        (key, str(value), str(value)))
        conn.commit()
    finally:
        conn.close()
    return jsonify(message='Settings saved')


# ── Admin PIN verification ────────────────────────────────────────────────────
PIN_MAX_ATTEMPTS = 5
PIN_LOCKOUT_SECS = 30 * 60  # 30 minutes

@app.route('/api/admin/verify_pin', methods=['POST'])
@login_required
def admin_verify_pin():
    """Verify the admin PIN after login. Sets pin_verified in session."""
    u = current_user()
    if not u or not u['is_admin']:
        return jsonify(error='Admin access required'), 403

    pin = (request.form.get('pin') or '').strip()
    if not pin:
        return jsonify(error='PIN is required'), 400

    uid = u['id']
    conn = get_db()
    try:
        with conn.cursor() as cur:
            # Check lockout
            cur.execute(
                'SELECT attempts, locked_until FROM admin_pin_attempts WHERE user_id=%s', (uid,))
            row = cur.fetchone()
            if row and row['locked_until']:
                import datetime
                if row['locked_until'] > datetime.datetime.now():
                    remaining = int((row['locked_until'] -
                                     datetime.datetime.now()).total_seconds())
                    mins, secs = divmod(remaining, 60)
                    return jsonify(
                        error=f'Too many wrong PINs. Try again in {mins}m {secs}s.'), 429

            # Get stored PIN hash
            cur.execute(
                "SELECT value FROM admin_settings WHERE key_name='admin_pin'")
            setting = cur.fetchone()
            if not setting:
                return jsonify(error='PIN not configured'), 500

            if not check_password_hash(setting['value'], pin):
                # Record failed attempt
                attempts = (row['attempts'] + 1) if row else 1
                import datetime
                locked_until = None
                if attempts >= PIN_MAX_ATTEMPTS:
                    locked_until = datetime.datetime.now() + \
                                   datetime.timedelta(seconds=PIN_LOCKOUT_SECS)
                    attempts = 0
                cur.execute("""
                    INSERT INTO admin_pin_attempts (user_id, attempts, locked_until)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        attempts=VALUES(attempts),
                        locked_until=VALUES(locked_until)
                """, (uid, attempts, locked_until))
                conn.commit()
                remaining_tries = PIN_MAX_ATTEMPTS - attempts
                if locked_until:
                    return jsonify(
                        error=f'Wrong PIN. Account locked for 30 minutes.'), 429
                return jsonify(
                    error=f'Wrong PIN. {remaining_tries} attempt(s) remaining.'), 401

            # Correct PIN — clear attempts, set session flag
            cur.execute(
                'DELETE FROM admin_pin_attempts WHERE user_id=%s', (uid,))
            conn.commit()

    finally:
        conn.close()

    session['pin_verified'] = True
    return jsonify(message='PIN verified. Welcome, Admin.')


@app.route('/api/admin/change_pin', methods=['POST'])
@admin_required
def admin_change_pin():
    """Change the admin PIN. Requires current PIN confirmation."""
    current_pin = (request.form.get('current_pin') or '').strip()
    new_pin     = (request.form.get('new_pin') or '').strip()

    if not current_pin or not new_pin:
        return jsonify(error='Current PIN and new PIN are required'), 400
    if len(new_pin) < 4:
        return jsonify(error='New PIN must be at least 4 digits'), 400
    if not new_pin.isdigit():
        return jsonify(error='PIN must contain digits only'), 400

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT value FROM admin_settings WHERE key_name='admin_pin'")
            setting = cur.fetchone()
            if not setting:
                return jsonify(error='PIN not configured'), 500
            if not check_password_hash(setting['value'], current_pin):
                return jsonify(error='Current PIN is incorrect'), 401
            cur.execute(
                "UPDATE admin_settings SET value=%s WHERE key_name='admin_pin'",
                (generate_password_hash(new_pin),))
        conn.commit()
    finally:
        conn.close()

    # Force re-verification on next admin action
    session.pop('pin_verified', None)
    return jsonify(message='PIN changed successfully.')


@app.route('/api/admin/change_credentials', methods=['POST'])
@admin_required
def admin_change_credentials():
    """Change admin email, username, and/or password. Requires current password."""
    u            = current_user()
    current_pass = (request.form.get('current_password') or '').strip()
    new_email    = (request.form.get('new_email') or '').strip().lower()
    new_username = (request.form.get('new_username') or '').strip().lower()
    new_password = (request.form.get('new_password') or '').strip()

    if not current_pass:
        return jsonify(error='Current password is required to make changes'), 400

    # Verify current password
    if not check_password_hash(u['password_hash'], current_pass):
        return jsonify(error='Current password is incorrect'), 401

    # Build update fields
    updates = []
    params  = []

    if new_email:
        # Basic email format check
        if '@' not in new_email or '.' not in new_email:
            return jsonify(error='Invalid email address'), 400
        updates.append('email=%s')
        params.append(new_email)

    if new_username:
        if len(new_username) < 3:
            return jsonify(error='Username must be at least 3 characters'), 400
        if not new_username.replace('_', '').replace('-', '').isalnum():
            return jsonify(error='Username can only contain letters, numbers, hyphens and underscores'), 400
        updates.append('username=%s')
        params.append(new_username)

    if new_password:
        if len(new_password) < 8:
            return jsonify(error='New password must be at least 8 characters'), 400
        updates.append('password_hash=%s')
        params.append(generate_password_hash(new_password))

    if not updates:
        return jsonify(error='No changes provided'), 400

    params.append(u['id'])
    conn = get_db()
    try:
        with conn.cursor() as cur:
            # Check uniqueness for email/username
            if new_email:
                cur.execute(
                    'SELECT id FROM users WHERE email=%s AND id!=%s',
                    (new_email, u['id']))
                if cur.fetchone():
                    return jsonify(error='That email is already in use'), 409
            if new_username:
                cur.execute(
                    'SELECT id FROM users WHERE username=%s AND id!=%s',
                    (new_username, u['id']))
                if cur.fetchone():
                    return jsonify(error='That username is already taken'), 409

            cur.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE id=%s",
                params)
        conn.commit()
    finally:
        conn.close()

    # If password changed, clear session so admin must log in again
    if new_password:
        session.clear()
        return jsonify(
            message='Credentials updated. Please log in again with your new password.',
            relogin=True)

    return jsonify(message='Credentials updated successfully.')


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    # Fix 1: Never run with debug=True in production.
    # Debug mode exposes the interactive debugger and full stack traces.
    _debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(debug=_debug, host='0.0.0.0', port=5000)
