# SMADS African Hits – Setup Guide
**Developer: CHIMBINI STEVEN | Zambia-first African Music Platform**
**Currency: Zambian Kwacha (ZMW)**

---

## Requirements
- Python 3.9+
- XAMPP (MySQL + phpMyAdmin)
- PyMySQL (`pip install PyMySQL`)

---

## Step 1 – Start XAMPP MySQL
Open XAMPP Control Panel → click **Start** next to **MySQL**

---

## Step 2 – Create Database in phpMyAdmin
1. Open `http://localhost/phpmyadmin`
2. Click **New** in the left sidebar
3. Database name: `smads_african_hits`
4. Collation: `utf8mb4_general_ci`
5. Click **Create**

> All tables are created automatically on first run.

---

## Step 3 – Install Python dependencies
```bash
cd music-site
pip install -r requirements.txt
```

---

## Step 4 – Configure environment variables (optional but recommended)
Copy the example env file and fill in your values:
```bash
copy api\.env.example .env
```

Then set them before running (Windows PowerShell):
```powershell
$env:SECRET_KEY    = "your-long-random-secret"
$env:DB_PASS       = "your-mysql-password"   # leave blank if XAMPP default
$env:ALERT_EMAIL_TO   = "you@email.com"
$env:ALERT_SMTP_USER  = "you@gmail.com"
$env:ALERT_SMTP_PASS  = "your-gmail-app-password"
```

> **Email setup (Gmail):** Enable 2FA → [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) → create App Password → use it as `ALERT_SMTP_PASS`. Without this, contact form messages are saved to the database but not emailed.

---

## Step 5 – Run the Flask server
```bash
python app.py
```

---

## Step 6 – Open the site
```
http://localhost:5000
```

---

## Default Admin Login

| Field    | Value                          |
|----------|-------------------------------|
| Email    | admin@smadsafricanhits.com    |
| Password | admin123                      |

⚠️ Change the password after first login!

---

## View Data in phpMyAdmin
While Flask is running, open `http://localhost/phpmyadmin`
Select `smads_african_hits` to browse:

| Table | Contents |
|-------|----------|
| `users` | Listeners, artists, admins |
| `tracks` | Uploaded music + chart scores |
| `likes` | Track likes |
| `comments` | Track comments |
| `payments` | ZMW upload payments |
| `playlists` | User playlists |
| `follows` | Artist follows |
| `play_history` | Play analytics by country |
| `reports` | Copyright/content reports |
| `contact_messages` | Contact form submissions |

---

## ZMW Pricing
| Plan | Price |
|------|-------|
| Single Track | K75 |
| Monthly Pro | K225/mo |
| Annual Pro | K1,800/yr (K150/mo) |

---

## Payment Methods Supported
- MTN Mobile Money
- Airtel Money
- Zamtel Kwacha
- Visa / Mastercard
- Bank Transfer

---

## African Genres Supported
Afrobeats, Amapiano, Highlife, Bongo Flava, Afro-Pop, Afro-Soul,
Gqom, Kwaito, Afro-Hip-Hop, Gospel, Zambian Music, R&B/Soul, Reggae

---

## System Features
- ✅ Free downloads for listeners (no account needed)
- ✅ Paid uploads for artists (ZMW pricing)
- ✅ African Hits Chart System (daily/weekly/monthly)
- ✅ Rising Stars section (new tracks with high engagement)
- ✅ Artist verification badge system
- ✅ Analytics dashboard (plays, downloads, countries)
- ✅ Smart search (title, artist, genre, mood, region, tags)
- ✅ Content reporting system
- ✅ Admin moderation (ban users, remove tracks, verify artists)
- ✅ Play history tracking by country

---

## Custom MySQL Password
If your XAMPP MySQL has a password, edit `app.py`:
```python
'password': os.environ.get('DB_PASS', 'your_password_here'),
```
Or set environment variable:
```bash
set DB_PASS=yourpassword
python app.py
```

## Production Environment Variables
```powershell
$env:SECRET_KEY    = "long-random-string-minimum-32-chars"
$env:DB_PASS       = "your_db_password"
$env:FLASK_ENV     = "production"
$env:ALLOWED_HOSTS = "yourdomain.com,www.yourdomain.com"
$env:SITE_URL      = "https://yourdomain.com"
python app.py
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Can't connect to MySQL` | Start MySQL in XAMPP first |
| `Unknown database` | Create `smads_african_hits` in phpMyAdmin |
| `ModuleNotFoundError: pymysql` | Run `pip install PyMySQL` |
| Login not working | Must run `python app.py`, not open HTML directly |
| Port 5000 in use | Change port in last line of `app.py` |
