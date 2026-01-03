import re
import sys
import random
import requests

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000"

def extract_csrf(html: str) -> str:
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    return m.group(1) if m else ''

def extract_dev_code(html: str) -> str:
    m = re.search(r'確認コードは\s*<strong>(\d{4})</strong>', html)
    return m.group(1) if m else ''

def main():
    s = requests.Session()
    # Register
    r = s.get(f"{BASE}/register")
    csrf = extract_csrf(r.text)
    if not csrf:
        print("Failed to get CSRF token on /register")
        sys.exit(1)
    suffix = random.randint(1000, 999999)
    username = f"@testuser{suffix}"
    email = f"test{suffix}@example.com"
    password = "PasswordA1"
    r2 = s.post(f"{BASE}/register", data={
        "username": username,
        "email": email,
        "password": password,
        "csrf_token": csrf,
    }, allow_redirects=True)
    # Verify page
    v = s.get(f"{BASE}/verify")
    vcsrf = extract_csrf(v.text)
    code = extract_dev_code(v.text)
    if not vcsrf:
        print("Failed to get CSRF token on /verify")
        sys.exit(1)
    if not code:
        print("Dev code not visible; SMTP likely configured. Skipping auto verify.")
        sys.exit(2)
    v2 = s.post(f"{BASE}/verify", data={
        "email": email,
        "code": code,
        "csrf_token": vcsrf,
    }, allow_redirects=True)
    # Check index logged-in
    idx = s.get(f"{BASE}/")
    if '<form action="/post"' in idx.text:
        print("OK: Logged in and post form visible")
        sys.exit(0)
    else:
        print("FAIL: Not logged in or verify failed")
        sys.exit(3)

if __name__ == "__main__":
    main()
