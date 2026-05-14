import os
pages = [f for f in os.listdir('.') if f.endswith('.html') and f != 'admin.html']
for page in sorted(pages):
    content = open(page, encoding='utf-8', errors='replace').read()
    has_logout = 'id="logout-btn"' in content
    has_mobile = 'id="logout-btn-mobile"' in content
    if not has_logout or not has_mobile:
        print(f'MISSING  {page}: logout-btn={has_logout}, mobile={has_mobile}')
    else:
        print(f'OK       {page}')
