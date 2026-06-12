4# SMADS African Hits — Code Standards & Audit Rules

This steering file documents all bugs found and fixed during the full 7-module audit.
Use it to prevent the same issues from reappearing.

---

## Module 1 — Auth

- **Email validation**: Always check `@` and domain on register — backend AND frontend.
- **Display name**: Reject whitespace-only values after `.strip()`.
- **Username format**: Must match `^[a-z0-9_\-]{3,60}$`.
- **Suspended check**: Check `is_active` BEFORE recording failed login attempts.
- **Password reset**: After successful reset, auto-redirect to home after 3 seconds.
- **Form clearing**: Clear login/register forms on logout (`loginForm.reset()`).
- **Verification banner**: Remove banner when user verifies or logs out — don't leave it stuck.
- **Resend verification**: Rate-limited to 3 per hour on the backend (tracked in `login_history`).
- **`doLogout`**: Must be a global function, not scoped inside `initAuthModal()`.
- **Profile page**: Has `Cache-Control: no-store` meta tags. Auth check redirects immediately with no delay.
- **`loadCurrentUser`**: Only call once per page — don't call it twice on profile.html.

---

## Module 2 — Upload & Payment

- **Cover art**: Not required — don't label it with `*` as if it is.
- **File validation in step 2**: Validate audio file is selected BEFORE proceeding to payment step.
- **Payment flow order**: Initiate payment → Confirm payment → Upload track. Never confirm before upload succeeds.
- **DB before file save**: Insert DB record first. Save file to disk only after DB succeeds. Roll back DB if file save fails.
- **CSRF on multipart**: `WTF_CSRF_CHECK_DEFAULT = False` — we handle CSRF manually via `X-CSRFToken` header.
- **Terms checkbox**: Must have `id`, `required` attribute, and a visible `*` indicator.
- **Order summary**: Must update dynamically when plan is selected — never hardcode amounts.
- **Broken icons**: Use HTML entities (`&#127881;`, `&#8594;` etc.) — never raw emoji in HTML files.

---

## Module 3 — Music Player & Browse

- **Sidebar filters**: Genre checkboxes must have `value` attributes. Read `.value`, not `.textContent`.
- **Duration filter**: Applied client-side after API fetch (API doesn't support it yet).
- **Player tags**: Populated dynamically from `track.tags` + `track.genre` — never hardcoded.
- **Comment count**: Updated from real API response in `loadComments()`.
- **Progress times**: Reset to `0:00` when no track loaded. Total time set from `track.duration`.
- **"More from" heading**: Set to real artist name when track loads.
- **Play count rate limit**: Max 1 play per IP per track per 10 minutes (in-memory cache on `track_play`).
- **Share endpoint**: No `@login_required` — sharing is public.
- **Pagination**: Use `-` not en-dash `–` to avoid encoding corruption.

---

## Module 4 — Profile & Dashboard

- **Settings save**: Use `#settings-display-name`, `#settings-bio`, `#settings-website` IDs — never `[name="display_name"]` which matches auth modal fields.
- **`user_update`**: Validate `display_name` explicitly — don't use MySQL `IF()` fallback.
- **Avatar upload**: Wired to `#avatar-edit-btn` → `#avatar-file-input` → `/api/user/update_avatar`. Validates size and MIME type.
- **Email in settings**: Show user's own email (read-only) from `appState.currentUser.email`.
- **Notification prefs**: Save/load from `localStorage` with a Save button.
- **Dead code**: Remove blank `addEventListener('click', () => {})` listeners.
- **`user_profile` API**: Include `email` in response for the settings tab.

---

## Module 5 — Admin Panel

- **Fake data**: Never hardcode user/payment rows in HTML. Always start with "Loading..." and fill from API.
- **`note` variable**: Always declare before use — `const note = document.getElementById('grant-note').value`.
- **Settings inputs**: Must have `name` attributes for the save handler to read them.
- **Currency**: Payments table shows `${p.amount}` — the backend already adds `K` prefix. Never add `$` prefix.
- **`/api/admin/stats`**: Requires admin login — non-admins get zeros only.
- **`resolve_report`**: Validate `report_id` as integer and check it exists before updating.
- **PIN check probe**: Use `/api/admin/ping` (lightweight) not `/api/admin/stats` (heavy DB query).
- **`admin_settings`**: Must actually save to `admin_settings` table — not just return success.

---

## Module 6 — Static Pages

- **Contact layout**: The `contact-layout` grid wrapper div must wrap both the methods column and the form column.
- **Timezone**: Use "CAT" (Central Africa Time) not "EST" — platform is Zambia-based.
- **FAQ search**: Must search across all tabs, not just the active one. Show all tab contents when searching.
- **FAQ arrows**: Use `&#8964;` (chevron) not raw `?` placeholder.
- **`loadCurrentUser`**: Must be `await`ed inside an `async` IIFE — never called bare.
- **Copyright**: Use `&copy;` once — never `© &copy;` (double prefix).
- **Timeline dashes**: Use `&mdash;` — never raw `—` or `?` corrupted characters.

---

## Module 7 — Backend & Security

- **`debug=True`**: NEVER in production. Use `FLASK_DEBUG=1` env var to enable in dev only.
- **`SECRET_KEY`**: Must be set via environment variable. Warn loudly if using the insecure default.
- **Admin seed password**: Never hardcode `admin123`. Use `ADMIN_INITIAL_PASSWORD` env var or generate a random one and print it once.
- **`X-Forwarded-For`**: Only trust when `TRUST_PROXY` env var is set — prevents IP spoofing to bypass rate limits.
- **Rate limiters**: In-memory — reset on restart. Document this. For production, use Redis-backed storage.
- **Session lifetime**: 7 days max (`timedelta(days=7)`), not 30.
- **`user_follow`**: Always verify target user exists and is active before inserting.
- **`.env` loading**: Use `python-dotenv` to load `api/.env` in development.
- **`admin_settings`**: Whitelist allowed keys before saving to DB.

---

## General Rules (apply everywhere)

### HTML
- All emoji/icons: Use HTML entities (`&#127925;`, `&#10003;`, `&times;`, `&mdash;` etc.) — never raw emoji in HTML files saved on Windows. They corrupt to `??`.
- Modal close buttons: Always `<button class="modal-close" aria-label="Close">&times;</button>`.
- Toast icon: `<span class="toast-icon">&#10003;</span>`.
- Footer social: Use `&#120143;` (Twitter), `&#128247;` (Instagram), `&#9654;` (YouTube), `&#128172;` (Discord).
- Mobile logout: `&#128682; Logout`.

### JavaScript
- Always `await loadCurrentUser()` inside an `async` IIFE.
- Use specific element IDs for form reads — never `querySelector('[name="..."]')` which can match multiple elements.
- Guard against `null` trackId/userId before API calls.
- Disable submit buttons during async operations, re-enable in `finally`.

### Python / Flask
- All DB queries use parameterized `%s` — never string concatenation.
- File saves happen AFTER DB insert succeeds.
- Integer inputs: always `int(value or 0)` wrapped in `try/except (ValueError, TypeError)`.
- Validate existence before update/delete — return 404 if not found.
- `@login_required` on all user-specific endpoints. `@admin_required` on all admin endpoints.
- Never expose internal error details — use generic 500 messages.
