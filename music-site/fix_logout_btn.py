import os, re

pages_missing_desktop = ['about.html', 'browse.html', 'contact.html', 'faq.html',
                          'index.html', 'player.html']

logout_btn = '<button class="btn btn-outline btn-sm" id="logout-btn" style="display:none">Logout</button>'

for page in pages_missing_desktop:
    content = open(page, encoding='utf-8', errors='replace').read()
    if 'id="logout-btn"' in content:
        print(f'SKIP {page} - already has logout-btn')
        continue
    # Insert logout button after the nav-profile link
    pattern = r'(<a href="profile\.html"[^>]*class="[^"]*nav-profile[^"]*"[^>]*>[^<]*</a>)'
    if re.search(pattern, content):
        new_content = re.sub(pattern, r'\1\n    ' + logout_btn, content)
        open(page, 'w', encoding='utf-8').write(new_content)
        print(f'FIXED {page}')
    else:
        print(f'WARN  {page} - nav-profile link not found, skipping')

# Fix reset-password.html and homepage.html separately (no nav-profile link)
for page in ['reset-password.html', 'homepage.html']:
    if not os.path.exists(page):
        continue
    content = open(page, encoding='utf-8', errors='replace').read()
    if 'id="logout-btn"' in content:
        print(f'SKIP {page}')
        continue
    # These pages may not have a full nav — skip if no nav-actions div
    if 'nav-actions' not in content:
        print(f'SKIP {page} - no nav-actions')
        continue
    pattern = r'(<a href="profile\.html"[^>]*class="[^"]*nav-profile[^"]*"[^>]*>[^<]*</a>)'
    if re.search(pattern, content):
        new_content = re.sub(pattern, r'\1\n    ' + logout_btn, content)
        open(page, 'w', encoding='utf-8').write(new_content)
        print(f'FIXED {page}')
    else:
        print(f'WARN  {page} - nav-profile not found')

print('Done.')
