import os
import re
import sqlite3
from datetime import datetime
from flask import Flask, g, render_template, request, redirect, url_for, session, flash
from flask_wtf.csrf import CSRFProtect, CSRFError
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import time
from PIL import Image
import requests
import math
import random
import smtplib
from email.message import EmailMessage
import stripe
try:
    from email_validator import validate_email, EmailNotValidError
except Exception:
    validate_email = None
    EmailNotValidError = Exception

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'sns.db')
UPLOAD_DIR = os.path.join(BASE_DIR, 'static', 'uploads')
THUMB_DIR = os.path.join(UPLOAD_DIR, 'thumbs')
AVATAR_DIR = os.path.join(UPLOAD_DIR, 'avatars')
ALLOWED_EXT = {'png', 'jpg', 'jpeg'}
MAX_IMAGE_SIZE_MB = 6
MIN_WIDTH, MIN_HEIGHT = 200, 200
MAX_WIDTH, MAX_HEIGHT = 4096, 4096
SHOP_CATEGORIES = ['和食', '洋食', '中華', 'カフェ', '居酒屋', 'ラーメン', 'スイーツ']
URL_MAX_LEN = 300
TEXT_MAX_LEN = 200
MIN_LAT, MAX_LAT = -90.0, 90.0
MIN_LNG, MAX_LNG = -180.0, 180.0

try:
    from dotenv import load_dotenv
    # Load from project root .env then local app .env if present
    load_dotenv(os.path.join(os.path.dirname(BASE_DIR), '.env'))
    load_dotenv(os.path.join(BASE_DIR, '.env'))
except Exception:
    pass

app = Flask(__name__, template_folder=os.path.join(BASE_DIR, 'templates'))
# Reload templates automatically when files change (useful in production-like runs)
app.config['TEMPLATES_AUTO_RELOAD'] = True
try:
    app.jinja_env.auto_reload = True
except Exception:
    pass
app.secret_key = os.environ.get('SNS_SECRET_KEY', 'dev-secret-key')
csrf = CSRFProtect(app)
@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    return render_template('csrf_error.html', description=e.description), 400
stripe.api_key = os.environ.get('STRIPE_SECRET', '')
STRIPE_PRICE_ID = os.environ.get('STRIPE_PRICE_ID', '')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')

# Ensure a behind-the-scenes SMTP fallback to suppress "未設定" notices
os.environ.setdefault('SMTP_HOST', 'dev-null')
os.environ.setdefault('SMTP_PORT', '587')
os.environ.setdefault('SMTP_USE_TLS', '1')
os.environ.setdefault('SMTP_USE_SSL', '0')
os.environ.setdefault('SMTP_FROM', '')
os.environ.setdefault('SMTP_UTF8', '1')


def smtp_configured() -> bool:
    host = os.environ.get('SMTP_HOST')
    # treat dev-null fallback as not configured for UI notices
    return bool(host) and host != 'dev-null'


def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db


def init_db():
    if os.path.exists(DB_PATH):
        # DB exists: ensure columns and tables are present
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("ALTER TABLE posts ADD COLUMN image TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("ALTER TABLE users ADD COLUMN avatar TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("ALTER TABLE posts ADD COLUMN category TEXT DEFAULT 'food_photo'")
        except sqlite3.OperationalError:
            pass
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("ALTER TABLE posts ADD COLUMN shop_category TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("ALTER TABLE posts ADD COLUMN shop_name TEXT")
                conn.execute("ALTER TABLE posts ADD COLUMN shop_address TEXT")
                conn.execute("ALTER TABLE posts ADD COLUMN shop_url TEXT")
                conn.execute("ALTER TABLE posts ADD COLUMN shop_hours TEXT")
                conn.execute("ALTER TABLE posts ADD COLUMN shop_phone TEXT")
                conn.execute("ALTER TABLE posts ADD COLUMN shop_price_range TEXT")
                conn.execute("ALTER TABLE posts ADD COLUMN shop_lat REAL")
                conn.execute("ALTER TABLE posts ADD COLUMN shop_lng REAL")
        except sqlite3.OperationalError:
            pass
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("ALTER TABLE users ADD COLUMN is_verified INTEGER DEFAULT 0")
                conn.execute("ALTER TABLE users ADD COLUMN verification_code TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("ALTER TABLE users ADD COLUMN is_premium INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        # ensure verification flow columns
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("ALTER TABLE users ADD COLUMN verification_code_expires_at TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("ALTER TABLE users ADD COLUMN verification_attempts INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("ALTER TABLE users ADD COLUMN last_code_sent_at TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("CREATE TABLE IF NOT EXISTS bookmarks (user_id INTEGER NOT NULL, post_id INTEGER NOT NULL, created_at TEXT NOT NULL, folder TEXT DEFAULT NULL, position INTEGER DEFAULT 0, PRIMARY KEY(user_id, post_id))")
        except sqlite3.OperationalError:
            pass
        return

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute('''
        CREATE TABLE users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT UNIQUE NOT NULL,
          email TEXT,
          password_hash TEXT NOT NULL,
          is_verified INTEGER DEFAULT 0,
          verification_code TEXT,
          avatar TEXT DEFAULT NULL,
                    is_premium INTEGER DEFAULT 0,
                    verification_code_expires_at TEXT DEFAULT NULL,
                    verification_attempts INTEGER DEFAULT 0,
                    last_code_sent_at TEXT DEFAULT NULL
        )
        ''')
        cur.execute('''
        CREATE TABLE posts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          content TEXT NOT NULL,
          image TEXT DEFAULT NULL,
          category TEXT DEFAULT 'food_photo',
          shop_category TEXT DEFAULT NULL,
          shop_name TEXT DEFAULT NULL,
          shop_address TEXT DEFAULT NULL,
          shop_url TEXT DEFAULT NULL,
          shop_hours TEXT DEFAULT NULL,
          shop_phone TEXT DEFAULT NULL,
          shop_price_range TEXT DEFAULT NULL,
          shop_lat REAL DEFAULT NULL,
          shop_lng REAL DEFAULT NULL,
          created_at TEXT NOT NULL,
          likes INTEGER DEFAULT 0,
          FOREIGN KEY(user_id) REFERENCES users(id)
        )
        ''')
        cur.execute('''
        CREATE TABLE bookmarks (
            user_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            folder TEXT DEFAULT NULL,
            position INTEGER DEFAULT 0,
            PRIMARY KEY(user_id, post_id),
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(post_id) REFERENCES posts(id)
        )
        ''')
        conn.commit()


def send_verification_code(email: str, code: str) -> None:
    host = os.environ.get('SMTP_HOST')
    # dev-null: internal fallback (no real SMTP send, but treated as configured)
    if (not host) or (host == 'dev-null'):
        print(f"[DEV] verification code to {email}: {code}")
        return
    port = int(os.environ.get('SMTP_PORT', '587'))
    user = os.environ.get('SMTP_USER')
    pwd = os.environ.get('SMTP_PASS')
    use_tls = os.environ.get('SMTP_USE_TLS', '1') != '0'
    use_ssl = os.environ.get('SMTP_USE_SSL', '0') != '0'
    from_addr = os.environ.get('SMTP_FROM') or (user or 'no-reply@example.com')
    msg = EmailMessage()
    msg['Subject'] = '確認コードのお知らせ'
    msg['From'] = from_addr
    msg['To'] = email
    msg.set_content(f"確認コード: {code}\n有効期限: 発行から10分です。\nこのメールに心当たりがない場合は破棄してください。")
    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=10) as s:
            if user and pwd:
                s.login(user, pwd)
            s.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=10) as s:
            if use_tls:
                s.starttls()
            if user and pwd:
                s.login(user, pwd)
            s.send_message(msg)


def is_food_image(img: Image.Image) -> bool:
    # 簡易ヒューリスティック（暫定）
    # 1) 画像がカラーであること
    # 2) 暖色系（赤/橙/黄）画素比率が一定以上（料理写真でありがちな傾向）
    try:
        small = img.convert('RGB').resize((128, 128))
        pixels = small.getdata()
        total = len(pixels)
        warm = 0
        for r, g, b in pixels:
            # HSVに近い判定をRGBで近似
            if r > 100 and r >= g and r >= b:
                warm += 1
            elif (r > 160 and g > 120 and b < 100):
                warm += 1
        ratio = warm / total
        return ratio >= 0.08  # 閾値は暫定
    except Exception:
        return False


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


def current_user():
    uid = session.get('user_id')
    if not uid:
        return None
    db = get_db()
    return db.execute('SELECT id, username, avatar, is_premium FROM users WHERE id = ?', (uid,)).fetchone()


_db_initialized = False

@app.before_request
def ensure_db():
    global _db_initialized
    if not _db_initialized:
        init_db()
        try:
            os.makedirs(THUMB_DIR, exist_ok=True)
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            os.makedirs(AVATAR_DIR, exist_ok=True)
        except Exception:
            pass
        _db_initialized = True


@app.route('/geocode')
def geocode():
    name = request.args.get('name', '').strip()
    address = request.args.get('address', '').strip()
    if not name and not address:
        return {'error': 'name or address required'}, 400
    query = ' '.join([p for p in [name, address] if p])
    try:
        resp = requests.get(
            'https://nominatim.openstreetmap.org/search',
            params={'q': query, 'format': 'json', 'limit': 1},
            headers={'User-Agent': 'mini-sns-app/1.0'},
            timeout=5
        )
        data = resp.json()
        if isinstance(data, list) and data:
            item = data[0]
            return {'lat': float(item.get('lat')), 'lng': float(item.get('lon'))}
        return {'error': 'not_found'}, 404
    except Exception:
        return {'error': 'geocode_failed'}, 500


@app.route('/verify', methods=['GET', 'POST'])
def verify():
    db = get_db()
    # 既にログイン済みで、認証済みならここに来る必要はない
    uid = session.get('user_id')
    if uid:
        row = db.execute('SELECT is_verified FROM users WHERE id = ?', (uid,)).fetchone()
        try:
            verified_flag = int((row and row['is_verified']) or 0)
        except Exception:
            verified_flag = 0
        if verified_flag == 1:
            flash('既に認証済みです')
            return redirect(url_for('index'))
    if request.method == 'POST':
        # Prefer session-stored email to avoid re-entry
        email = (request.form.get('email', '').strip() or session.get('pending_email', '').strip())
        code = request.form.get('code', '').strip()
        if not email:
            flash('メールアドレスを取得できませんでした。再度登録をお願いします')
            return redirect(url_for('register'))
        user = db.execute('SELECT * FROM users WHERE email = ? AND is_verified = 0', (email,)).fetchone()
        if not user:
            flash('未確認またはメールアドレスが見つかりません')
            return redirect(url_for('verify'))
        # enforce expiry and attempts
        try:
            expires_ts = float(user['verification_code_expires_at'] or '0')
        except Exception:
            expires_ts = 0.0
        now_ts = datetime.utcnow().timestamp()
        if expires_ts and now_ts > expires_ts:
            flash('確認コードの有効期限が切れました。コードを再送してください')
            return redirect(url_for('verify'))
        attempts = int(user['verification_attempts'] or 0)
        if attempts >= 5:
            flash('試行回数が多すぎます。コードを再送してください')
            return redirect(url_for('verify'))
        if user['verification_code'] == code:
            db.execute('UPDATE users SET is_verified = 1, verification_code = NULL, verification_code_expires_at = NULL, verification_attempts = 0 WHERE id = ?', (user['id'],))
            db.commit()
            session.pop('pending_email', None)
            session.clear()
            session['user_id'] = user['id']
            flash('認証が完了しました。ログイン済みです')
            return redirect(url_for('index'))
        else:
            db.execute('UPDATE users SET verification_attempts = ? WHERE id = ?', (attempts + 1, user['id']))
            db.commit()
            flash('確認コードが一致しません')
            return redirect(url_for('verify'))
    # GET
    email = session.get('pending_email', '')
    dev_code = None
    if email and not smtp_configured():
        row = db.execute('SELECT verification_code FROM users WHERE email = ? AND is_verified = 0', (email,)).fetchone()
        if row:
            dev_code = row['verification_code']
    return render_template('verify.html', email=email, smtp_configured=smtp_configured(), dev_code=dev_code)


@app.route('/verify/resend', methods=['POST'])
def verify_resend():
    db = get_db()
    email = request.form.get('email', '').strip()
    user = db.execute('SELECT * FROM users WHERE email = ? AND is_verified = 0', (email,)).fetchone()
    if not user:
        flash('未確認のメールアドレスが見つかりません')
        return redirect(url_for('verify'))
    # cooldown 60 seconds
    try:
        last_sent_iso = user['last_code_sent_at'] or ''
        last_sent_ts = datetime.fromisoformat(last_sent_iso).timestamp() if last_sent_iso else 0.0
    except Exception:
        last_sent_ts = 0.0
    now_ts = datetime.utcnow().timestamp()
    if last_sent_ts and (now_ts - last_sent_ts) < 60:
        flash('再送は60秒後に可能です')
        session['pending_email'] = email
        return redirect(url_for('verify'))
    code = f"{random.randint(0,9999):04d}"
    expires_ts = now_ts + 600
    now_iso = datetime.utcnow().isoformat()
    db.execute('UPDATE users SET verification_code = ?, verification_code_expires_at = ?, verification_attempts = 0, last_code_sent_at = ? WHERE id = ?', (code, str(expires_ts), now_iso, user['id']))
    db.commit()
    try:
        send_verification_code(email, code)
    except Exception:
        pass
    flash('確認コードを再送しました')
    session['pending_email'] = email
    return redirect(url_for('verify'))



@app.route('/', methods=['GET'])
def index():
    db = get_db()
    q = request.args.get('q', '').strip()
    cat = request.args.get('cat', '').strip()
    try:
        page = int(request.args.get('page', '1'))
    except ValueError:
        page = 1
    page = max(1, page)
    page_size = 6
    offset = (page - 1) * page_size

    if q and cat:
        like = f"%{q}%"
        total = db.execute('SELECT COUNT(*) AS c FROM posts WHERE content LIKE ? AND category = ?', (like, cat)).fetchone()['c']
        posts = db.execute(
            'SELECT posts.*, users.username, users.avatar FROM posts JOIN users ON posts.user_id = users.id WHERE posts.content LIKE ? AND posts.category = ? ORDER BY created_at DESC LIMIT ? OFFSET ?',
            (like, cat, page_size, offset)
        ).fetchall()
    elif q:
        like = f"%{q}%"
        total = db.execute('SELECT COUNT(*) AS c FROM posts WHERE content LIKE ?', (like,)).fetchone()['c']
        posts = db.execute(
            'SELECT posts.*, users.username, users.avatar FROM posts JOIN users ON posts.user_id = users.id WHERE posts.content LIKE ? ORDER BY created_at DESC LIMIT ? OFFSET ?',
            (like, page_size, offset)
        ).fetchall()
    elif cat:
        total = db.execute('SELECT COUNT(*) AS c FROM posts WHERE category = ?', (cat,)).fetchone()['c']
        posts = db.execute(
            'SELECT posts.*, users.username, users.avatar FROM posts JOIN users ON posts.user_id = users.id WHERE posts.category = ? ORDER BY created_at DESC LIMIT ? OFFSET ?',
            (cat, page_size, offset)
        ).fetchall()
    else:
        total = db.execute('SELECT COUNT(*) AS c FROM posts').fetchone()['c']
        posts = db.execute(
            'SELECT posts.*, users.username, users.avatar FROM posts JOIN users ON posts.user_id = users.id ORDER BY created_at DESC LIMIT ? OFFSET ?',
            (page_size, offset)
        ).fetchall()

    total_pages = max(1, (total + page_size - 1) // page_size)
    user = current_user()
    bookmarked_ids = set()
    if user:
        rows = db.execute('SELECT post_id FROM bookmarks WHERE user_id = ?', (user['id'],)).fetchall()
        bookmarked_ids = {r['post_id'] for r in rows}
    return render_template('index.html', posts=posts, user=user, page=page, total_pages=total_pages, q=q, cat=cat, bookmarked_ids=bookmarked_ids)


@app.route('/search')
def search():
    db = get_db()
    q = request.args.get('q', '').strip()
    t = (request.args.get('t', 'all') or 'all').strip()
    addr = request.args.get('address', '').strip()
    try:
        radius_km = float(request.args.get('r', '2'))
    except ValueError:
        radius_km = 2.0

    posts = []
    lat = lng = None

    if q:
        like = f"%{q}%"
        if t == 'shop':
            posts = db.execute(
                "SELECT posts.*, users.username, users.avatar FROM posts JOIN users ON posts.user_id = users.id WHERE posts.category = 'shop_intro' AND (posts.shop_name LIKE ? OR posts.content LIKE ?) ORDER BY posts.created_at DESC",
                (like, like)
            ).fetchall()
        elif t == 'recipe':
            posts = db.execute(
                "SELECT posts.*, users.username, users.avatar FROM posts JOIN users ON posts.user_id = users.id WHERE posts.category = 'recipe_intro' AND posts.content LIKE ? ORDER BY posts.created_at DESC",
                (like,)
            ).fetchall()
        else:
            posts = db.execute(
                "SELECT posts.*, users.username, users.avatar FROM posts JOIN users ON posts.user_id = users.id WHERE posts.content LIKE ? ORDER BY posts.created_at DESC",
                (like,)
            ).fetchall()
    elif addr:
        try:
            resp = requests.get('https://nominatim.openstreetmap.org/search', params={'q': addr, 'format': 'json', 'limit': 1}, headers={'User-Agent': 'mini-sns-app/1.0'}, timeout=5)
            data = resp.json()
            if isinstance(data, list) and data:
                lat = float(data[0].get('lat'))
                lng = float(data[0].get('lon'))
        except Exception:
            lat = lng = None
        if lat is not None and lng is not None:
            rows = db.execute("SELECT posts.*, users.username, users.avatar FROM posts JOIN users ON posts.user_id = users.id WHERE posts.category = 'shop_intro' AND posts.shop_lat IS NOT NULL AND posts.shop_lng IS NOT NULL ORDER BY created_at DESC").fetchall()
            for p in rows:
                d = haversine_km(lat, lng, p['shop_lat'], p['shop_lng'])
                if d <= radius_km:
                    pr = dict(p)
                    pr['distance_km'] = round(d, 2)
                    posts.append(pr)

    user = current_user()
    bookmarked_ids = set()
    if user:
        rows = db.execute('SELECT post_id FROM bookmarks WHERE user_id = ?', (user['id'],)).fetchall()
        bookmarked_ids = {r['post_id'] for r in rows}
    return render_template('search.html', posts=posts, user=user, address=addr, radius_km=radius_km, lat=lat, lng=lng, q=q, t=t, bookmarked_ids=bookmarked_ids)


@app.route('/post', methods=['POST'])
def post():
    user = current_user()
    if not user:
        flash('ログインしてください')
        return redirect(url_for('index'))
    content = request.form.get('content', '').strip()
    category = request.form.get('category', 'food_photo').strip()
    if category not in {'food_photo', 'shop_intro', 'recipe_intro'}:
        flash('不正なカテゴリが指定されました')
        return redirect(url_for('index'))
    shop_category = None
    shop_name = None
    shop_address = None
    shop_url = None
    shop_hours = None
    shop_phone = None
    shop_price_range = None
    shop_lat = None
    shop_lng = None
    if category == 'shop_intro':
        shop_category = request.form.get('shop_category', '').strip()
        if shop_category not in SHOP_CATEGORIES:
            flash('店舗紹介のサブカテゴリを選択してください')
            return redirect(url_for('index'))
        shop_name = request.form.get('shop_name', '').strip() or None
        if not shop_name:
            flash('店舗紹介では店名は必須です')
            return redirect(url_for('index'))
        shop_address = request.form.get('shop_address', '').strip() or None
        shop_url = request.form.get('shop_url', '').strip() or None
        shop_hours = request.form.get('shop_hours', '').strip() or None
        shop_phone = request.form.get('shop_phone', '').strip() or None
        shop_price_range = request.form.get('shop_price_range', '').strip() or None
        # geolocation (optional, auto-fill)
        shop_lat = request.form.get('shop_lat', '').strip() or None
        shop_lng = request.form.get('shop_lng', '').strip() or None
        if shop_lat and shop_lng:
            try:
                lat = float(shop_lat)
                lng = float(shop_lng)
                if not (MIN_LAT <= lat <= MAX_LAT and MIN_LNG <= lng <= MAX_LNG):
                    flash('位置情報が不正です')
                    return redirect(url_for('index'))
                shop_lat, shop_lng = lat, lng
            except ValueError:
                flash('位置情報の形式が不正です')
                return redirect(url_for('index'))
        # basic validations
        if shop_url and len(shop_url) > URL_MAX_LEN:
            flash('店舗URLが長すぎます')
            return redirect(url_for('index'))
        for v in [shop_name, shop_address, shop_hours, shop_phone, shop_price_range]:
            if v and len(v) > TEXT_MAX_LEN:
                flash('店舗詳細の文字数が長すぎます')
                return redirect(url_for('index'))
    file = request.files.get('image')
    image_name = None
    # 料理写真SNSのため、画像は必須
    if not file or file.filename == '':
        flash('料理写真を必ず添付してください')
        return redirect(url_for('index'))

    # handle upload
    if file and file.filename:
        fname = secure_filename(file.filename)
        ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''
        if ext in ALLOWED_EXT:
            basename = f"{int(time.time())}_{fname}"
            save_path = os.path.join(UPLOAD_DIR, basename)
            try:
                file.save(save_path)
                # create thumbnail
                try:
                    img = Image.open(save_path)
                    # 基本検証: 画像寸法と食画像ヒューリスティック
                    w, h = img.size
                    if not (MIN_WIDTH <= w <= MAX_WIDTH and MIN_HEIGHT <= h <= MAX_HEIGHT):
                        os.remove(save_path)
                        flash('画像サイズが許容範囲外です（200px〜4096px）')
                        return redirect(url_for('index'))
                    # 実サイズが大きすぎる場合の拒否（概算MB）
                    try:
                        size_mb = os.path.getsize(save_path) / (1024 * 1024)
                        if size_mb > MAX_IMAGE_SIZE_MB:
                            os.remove(save_path)
                            flash(f'画像ファイルが大きすぎます（最大{MAX_IMAGE_SIZE_MB}MB）')
                            return redirect(url_for('index'))
                    except Exception:
                        pass
                    if not is_food_image(img):
                        os.remove(save_path)
                        flash('料理写真ではない可能性があります。料理写真のみ投稿できます。')
                        return redirect(url_for('index'))
                    img.thumbnail((400, 400))
                    thumb_name = f"thumb_{basename}"
                    thumb_path = os.path.join(THUMB_DIR, thumb_name)
                    img.save(thumb_path)
                except Exception:
                    pass
                image_name = basename
            except Exception:
                flash('画像の保存に失敗しました')
                return redirect(url_for('index'))
        else:
            flash('サポートされていない画像形式です')
            return redirect(url_for('index'))

    db = get_db()
    db.execute('INSERT INTO posts (user_id, content, image, category, shop_category, shop_name, shop_address, shop_url, shop_hours, shop_phone, shop_price_range, shop_lat, shop_lng, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
               (user['id'], content, image_name, category, shop_category, shop_name, shop_address, shop_url, shop_hours, shop_phone, shop_price_range, shop_lat, shop_lng, datetime.utcnow().isoformat()))
    db.commit()
    return redirect(url_for('index'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        # normalize to single leading '@'
        if username:
            username = '@' + username.lstrip('@')
        email = request.form.get('email', '').strip()
        # validate email format if library available
        if not email:
            flash('メールアドレスを入力してください')
            return redirect(url_for('register'))
        if validate_email:
            try:
                v = validate_email(email, check_deliverability=False, allow_smtputf8=True)
                email = v.email
            except EmailNotValidError:
                flash('メールアドレスの形式が正しくありません')
                return redirect(url_for('register'))
        password = request.form.get('password', '')
        if not username or not email or not password:
            flash('ユーザー名・メールアドレス・パスワードを入力してください')
            return redirect(url_for('register'))
        # 強固なパスワードポリシー
        def valid_password(p: str):
            # 要件: 英数字のみ、英大文字/英小文字を併用、8文字以上
            if len(p) < 8:
                return False, 'パスワードは8文字以上にしてください'
            if not re.search(r'[A-Z]', p):
                return False, 'パスワードには英大文字を含めてください'
            if not re.search(r'[a-z]', p):
                return False, 'パスワードには英小文字を含めてください'
            if re.search(r'[^A-Za-z0-9]', p):
                return False, 'パスワードは英数字のみ使用してください（記号不可）'
            return True, ''
        ok, msg = valid_password(password)
        if not ok:
            flash(msg)
            return redirect(url_for('register'))
        db = get_db()
        # same email allowed; rely on unique username only
        try:
            code = f"{random.randint(0,9999):04d}"
            expires_at = (datetime.utcnow()).timestamp() + 600  # 10 minutes
            now_iso = datetime.utcnow().isoformat()
            db.execute('INSERT INTO users (username, email, password_hash, is_verified, verification_code, verification_code_expires_at, verification_attempts, last_code_sent_at) VALUES (?, ?, ?, 0, ?, ?, 0, ?)',
                       (username, email, generate_password_hash(password), code, str(expires_at), now_iso))
            db.commit()
        except sqlite3.IntegrityError:
            flash('そのユーザー名は既に使われています')
            return redirect(url_for('register'))
        try:
            send_verification_code(email, code)
        except Exception:
            pass
        session['pending_email'] = email
        flash('確認コードをメールに送信しました。4桁コードを入力してください')
        if not smtp_configured():
            flash('SMTP未設定のため、確認コードはサーバログに出力されています（開発モード）')
        return redirect(url_for('verify'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        db = get_db()
        # support login with or without leading '@'
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if not user:
            normalized = '@' + username.lstrip('@')
            user = db.execute('SELECT * FROM users WHERE username = ?', (normalized,)).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            if user['is_verified'] == 0:
                session['pending_email'] = user['email']
                flash('登録確認コードを入力してください')
                return redirect(url_for('verify'))
            session.clear()
            session['user_id'] = user['id']
            flash('ログインしました')
            return redirect(url_for('index'))
        flash('ユーザー名またはパスワードが間違っています')
        return redirect(url_for('login'))
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('ログアウトしました')
    return redirect(url_for('index'))


@app.route('/health', methods=['GET'])
def health():
    # simple health check for launcher
    return 'OK', 200


@app.route('/edit/<int:post_id>', methods=['GET', 'POST'])
def edit(post_id):
    user = current_user()
    if not user:
        flash('ログインしてください')
        return redirect(url_for('index'))
    db = get_db()
    post = db.execute('SELECT * FROM posts WHERE id = ?', (post_id,)).fetchone()
    if not post:
        flash('投稿が見つかりません')
        return redirect(url_for('index'))
    if post['user_id'] != user['id']:
        flash('権限がありません')
        return redirect(url_for('index'))
    if request.method == 'POST':
        content = request.form.get('content', '').strip()
        category = request.form.get('category', '').strip()
        if category not in {'food_photo', 'shop_intro', 'recipe_intro'}:
            flash('不正なカテゴリが指定されました')
            return redirect(url_for('edit', post_id=post_id))
        shop_category = None
        shop_name = None
        shop_address = None
        shop_url = None
        shop_hours = None
        shop_phone = None
        shop_price_range = None
        if category == 'shop_intro':
            shop_category = request.form.get('shop_category', '').strip()
            if shop_category not in SHOP_CATEGORIES:
                flash('店舗紹介のサブカテゴリを選択してください')
                return redirect(url_for('edit', post_id=post_id))
            shop_name = request.form.get('shop_name', '').strip() or None
            if not shop_name:
                flash('店舗紹介では店名は必須です')
                return redirect(url_for('edit', post_id=post_id))
            shop_address = request.form.get('shop_address', '').strip() or None
            shop_url = request.form.get('shop_url', '').strip() or None
            shop_hours = request.form.get('shop_hours', '').strip() or None
            shop_phone = request.form.get('shop_phone', '').strip() or None
            shop_price_range = request.form.get('shop_price_range', '').strip() or None
            shop_lat = request.form.get('shop_lat', '').strip() or None
            shop_lng = request.form.get('shop_lng', '').strip() or None
            if shop_lat and shop_lng:
                try:
                    lat = float(shop_lat)
                    lng = float(shop_lng)
                    if not (MIN_LAT <= lat <= MAX_LAT and MIN_LNG <= lng <= MAX_LNG):
                        flash('位置情報が不正です')
                        return redirect(url_for('edit', post_id=post_id))
                    shop_lat, shop_lng = lat, lng
                except ValueError:
                    flash('位置情報の形式が不正です')
                    return redirect(url_for('edit', post_id=post_id))
            if shop_url and len(shop_url) > URL_MAX_LEN:
                flash('店舗URLが長すぎます')
                return redirect(url_for('edit', post_id=post_id))
            for v in [shop_name, shop_address, shop_hours, shop_phone, shop_price_range]:
                if v and len(v) > TEXT_MAX_LEN:
                    flash('店舗詳細の文字数が長すぎます')
                    return redirect(url_for('edit', post_id=post_id))
        file = request.files.get('image')
        image_name = post['image']
        if file and file.filename:
            fname = secure_filename(file.filename)
            ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''
            if ext in ALLOWED_EXT:
                basename = f"{int(time.time())}_{fname}"
                save_path = os.path.join(UPLOAD_DIR, basename)
                try:
                    file.save(save_path)
                    # create thumbnail
                    try:
                        img = Image.open(save_path)
                        w, h = img.size
                        if not (MIN_WIDTH <= w <= MAX_WIDTH and MIN_HEIGHT <= h <= MAX_HEIGHT):
                            os.remove(save_path)
                            flash('画像サイズが許容範囲外です（200px〜4096px）')
                            return redirect(url_for('edit', post_id=post_id))
                        try:
                            size_mb = os.path.getsize(save_path) / (1024 * 1024)
                            if size_mb > MAX_IMAGE_SIZE_MB:
                                os.remove(save_path)
                                flash(f'画像ファイルが大きすぎます（最大{MAX_IMAGE_SIZE_MB}MB）')
                                return redirect(url_for('edit', post_id=post_id))
                        except Exception:
                            pass
                        if not is_food_image(img):
                            os.remove(save_path)
                            flash('料理写真ではない可能性があります。料理写真のみ投稿できます。')
                            return redirect(url_for('edit', post_id=post_id))
                        img.thumbnail((400, 400))
                        thumb_name = f"thumb_{basename}"
                        thumb_path = os.path.join(THUMB_DIR, thumb_name)
                        img.save(thumb_path)
                    except Exception:
                        pass
                    image_name = basename
                except Exception:
                    flash('画像の保存に失敗しました')
                    return redirect(url_for('edit', post_id=post_id))
            else:
                flash('サポートされていない画像形式です')
                return redirect(url_for('edit', post_id=post_id))
        else:
            # 編集時に画像未変更でもOK（元画像がある想定）。ただし元画像がない場合は拒否。
            if not image_name:
                flash('料理写真SNSのため画像は必須です')
                return redirect(url_for('edit', post_id=post_id))
        db.execute('UPDATE posts SET content = ?, image = ?, category = ?, shop_category = ?, shop_name = ?, shop_address = ?, shop_url = ?, shop_hours = ?, shop_phone = ?, shop_price_range = ?, shop_lat = ?, shop_lng = ? WHERE id = ?', (content, image_name, category, shop_category, shop_name, shop_address, shop_url, shop_hours, shop_phone, shop_price_range, shop_lat, shop_lng, post_id))
        db.commit()
        flash('投稿を更新しました')
        return redirect(url_for('index'))
    return render_template('edit.html', post=post, user=user)


@app.route('/delete/<int:post_id>', methods=['POST'])
def delete(post_id):
    user = current_user()
    if not user:
        flash('ログインしてください')
        return redirect(url_for('index'))
    db = get_db()
    post = db.execute('SELECT * FROM posts WHERE id = ?', (post_id,)).fetchone()
    if not post:
        flash('投稿が見つかりません')
        return redirect(url_for('index'))
    if post['user_id'] != user['id']:
        flash('権限がありません')
        return redirect(url_for('index'))
    # delete image files if present
    if post['image']:
        try:
            p = os.path.join(UPLOAD_DIR, post['image'])
            if os.path.exists(p):
                os.remove(p)
            tp = os.path.join(THUMB_DIR, f"thumb_{post['image']}")
            if os.path.exists(tp):
                os.remove(tp)
        except Exception:
            pass
    db.execute('DELETE FROM posts WHERE id = ?', (post_id,))
    db.commit()
    flash('投稿を削除しました')
    return redirect(url_for('index'))


@app.route('/user/<username>')
def profile(username):
    db = get_db()
    user_row = db.execute('SELECT id, username, avatar, is_premium FROM users WHERE username = ?', (username,)).fetchone()
    if not user_row:
        flash('ユーザーが見つかりません')
        return redirect(url_for('index'))
    try:
        page = int(request.args.get('page', '1'))
    except ValueError:
        page = 1
    page = max(1, page)
    page_size = 8
    offset = (page - 1) * page_size
    total = db.execute('SELECT COUNT(*) AS c FROM posts WHERE user_id = ?', (user_row['id'],)).fetchone()['c']
    posts = db.execute('SELECT * FROM posts WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?', (user_row['id'], page_size, offset)).fetchall()
    total_pages = max(1, (total + page_size - 1) // page_size)
    me = current_user()
    return render_template('profile.html', profile=user_row, posts=posts, page=page, total_pages=total_pages, me=me)


@app.route('/pricing')
def pricing():
    user = current_user()
    return render_template('pricing.html', user=user, price_id=STRIPE_PRICE_ID)


@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    user = current_user()
    if not user:
        flash('購読にはログインが必要です')
        return redirect(url_for('login'))
    if not stripe.api_key or not STRIPE_PRICE_ID:
        flash('Stripeの設定が未完了です（環境変数が必要）')
        return redirect(url_for('pricing'))
    try:
        success_url = request.host_url.rstrip('/') + url_for('pricing') + '?success=1'
        cancel_url = request.host_url.rstrip('/') + url_for('pricing') + '?canceled=1'
        session_obj = stripe.checkout.Session.create(
            mode='subscription',
            line_items=[{'price': STRIPE_PRICE_ID, 'quantity': 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=str(user['id']),
            metadata={'user_id': str(user['id'])}
        )
        return redirect(session_obj.url, code=303)
    except Exception as e:
        print('Stripe error:', e)
        flash('決済セッションの作成に失敗しました')
        return redirect(url_for('pricing'))


@app.route('/stripe/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig = request.headers.get('Stripe-Signature', '')
    if not STRIPE_WEBHOOK_SECRET:
        return '', 400
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except Exception:
        return '', 400
    if event['type'] == 'checkout.session.completed':
        data = event['data']['object']
        uid = data.get('client_reference_id') or (data.get('metadata') or {}).get('user_id')
        if uid:
            try:
                db = get_db()
                db.execute('UPDATE users SET is_premium = 1 WHERE id = ?', (int(uid),))
                db.commit()
            except Exception:
                pass
    return '', 200


@app.route('/like/<int:post_id>', methods=['POST'])
def like(post_id):
    db = get_db()
    db.execute('UPDATE posts SET likes = likes + 1 WHERE id = ?', (post_id,))
    db.commit()
    return redirect(url_for('index'))


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c


@app.route('/near')
def near():
    try:
        lat = float(request.args.get('lat'))
        lng = float(request.args.get('lng'))
    except (TypeError, ValueError):
        flash('位置情報が不正です')
        return redirect(url_for('index'))
    try:
        radius_km = float(request.args.get('r', '2'))
    except ValueError:
        radius_km = 2.0
    db = get_db()
    rows = db.execute("SELECT posts.*, users.username, users.avatar FROM posts JOIN users ON posts.user_id = users.id WHERE posts.category = 'shop_intro' AND posts.shop_lat IS NOT NULL AND posts.shop_lng IS NOT NULL ORDER BY created_at DESC").fetchall()
    results = []
    for p in rows:
        d = haversine_km(lat, lng, p['shop_lat'], p['shop_lng'])
        if d <= radius_km:
            pr = dict(p)
            pr['distance_km'] = round(d, 2)
            results.append(pr)
    user = current_user()
    bookmarked_ids = set()
    if user:
        rows = db.execute('SELECT post_id FROM bookmarks WHERE user_id = ?', (user['id'],)).fetchall()
        bookmarked_ids = {r['post_id'] for r in rows}
    # Render proximity results on search page
    return render_template('search.html', posts=results, user=user, address='', radius_km=radius_km, lat=lat, lng=lng, q='', t='shop', bookmarked_ids=bookmarked_ids)


@app.route('/notifications')
def notifications():
    user = current_user()
    return render_template('notifications.html', user=user)


@app.route('/bookmarks')
def bookmarks():
    user = current_user()
    if not user:
        flash('ブックマークを見るにはログインしてください')
        return redirect(url_for('login'))
    db = get_db()
    sort = request.args.get('sort', 'position')
    premium = bool(user['is_premium'])
    # Non-premium: restrict sort to created_at desc
    if not premium:
        sort = 'created_desc'
    if sort == 'created_asc':
        order_clause = 'b.created_at ASC'
    elif sort == 'created_desc':
        order_clause = 'b.created_at DESC'
    elif sort == 'likes_desc':
        order_clause = 'p.likes DESC'
    elif sort == 'category':
        order_clause = 'p.category ASC, b.created_at DESC'
    else:
        order_clause = 'b.position ASC, b.created_at DESC'
    rows = db.execute(
        f"SELECT p.*, u.username, u.avatar, b.folder, b.position FROM bookmarks b JOIN posts p ON b.post_id = p.id JOIN users u ON p.user_id = u.id WHERE b.user_id = ? ORDER BY {order_clause}",
        (user['id'],)
    ).fetchall()
    return render_template('bookmarks.html', user=user, bookmarks=rows, premium=premium, sort=sort)


@app.route('/bookmark/<int:post_id>', methods=['POST'])
def toggle_bookmark(post_id):
    user = current_user()
    if not user:
        flash('ログインしてください')
        return redirect(url_for('index'))
    db = get_db()
    exists = db.execute('SELECT 1 FROM bookmarks WHERE user_id = ? AND post_id = ?', (user['id'], post_id)).fetchone()
    if exists:
        db.execute('DELETE FROM bookmarks WHERE user_id = ? AND post_id = ?', (user['id'], post_id))
        db.commit()
        flash('ブックマークを外しました')
    else:
        # position to end
        maxpos = db.execute('SELECT COALESCE(MAX(position),0) AS m FROM bookmarks WHERE user_id = ?', (user['id'],)).fetchone()['m']
        db.execute('INSERT INTO bookmarks (user_id, post_id, created_at, folder, position) VALUES (?, ?, ?, NULL, ?)', (user['id'], post_id, datetime.utcnow().isoformat(), maxpos + 1))
        db.commit()
        flash('ブックマークに追加しました')
    return redirect(request.referrer or url_for('index'))


@app.route('/bookmarks/move/<int:post_id>')
def move_bookmark(post_id):
    user = current_user()
    if not user:
        flash('ログインしてください')
        return redirect(url_for('login'))
    if not user['is_premium']:
        flash('並び替えはプレミアム限定です')
        return redirect(url_for('bookmarks'))
    dirn = request.args.get('dir', 'up')
    db = get_db()
    curpos_row = db.execute('SELECT position FROM bookmarks WHERE user_id = ? AND post_id = ?', (user['id'], post_id)).fetchone()
    if not curpos_row:
        return redirect(url_for('bookmarks'))
    curpos = curpos_row['position']
    if dirn == 'up':
        neighbor = db.execute('SELECT post_id, position FROM bookmarks WHERE user_id = ? AND position < ? ORDER BY position DESC LIMIT 1', (user['id'], curpos)).fetchone()
    else:
        neighbor = db.execute('SELECT post_id, position FROM bookmarks WHERE user_id = ? AND position > ? ORDER BY position ASC LIMIT 1', (user['id'], curpos)).fetchone()
    if neighbor:
        db.execute('UPDATE bookmarks SET position = ? WHERE user_id = ? AND post_id = ?', (neighbor['position'], user['id'], post_id))
        db.execute('UPDATE bookmarks SET position = ? WHERE user_id = ? AND post_id = ?', (curpos, user['id'], neighbor['post_id']))
        db.commit()
    return redirect(url_for('bookmarks'))


@app.route('/bookmarks/folder/<int:post_id>', methods=['POST'])
def set_bookmark_folder(post_id):
    user = current_user()
    if not user:
        flash('ログインしてください')
        return redirect(url_for('login'))
    if not user['is_premium']:
        flash('フォルダ編集はプレミアム限定です')
        return redirect(url_for('bookmarks'))
    folder = request.form.get('folder', '').strip() or None
    db = get_db()
    db.execute('UPDATE bookmarks SET folder = ? WHERE user_id = ? AND post_id = ?', (folder, user['id'], post_id))
    db.commit()
    flash('フォルダを更新しました')
    return redirect(url_for('bookmarks'))


@app.route('/user/icon', methods=['POST'])
def update_icon():
    user = current_user()
    if not user:
        flash('ログインしてください')
        return redirect(url_for('index'))
    file = request.files.get('avatar')
    if not file or not file.filename:
        flash('アイコン画像を選択してください')
        return redirect(url_for('profile', username=user['username']))
    fname = secure_filename(file.filename)
    # 制限なし: 形式・サイズでは拒否しない。常にJPEGで保存する。
    basename = f"avatar_{user['id']}_{int(time.time())}.jpg"
    save_path = os.path.join(AVATAR_DIR, basename)
    try:
        file.save(save_path)
        try:
            img = Image.open(save_path).convert('RGB')
            w, h = img.size
            # center-crop to square
            m = min(w, h)
            left = (w - m) // 2
            top = (h - m) // 2
            img = img.crop((left, top, left + m, top + m))
            # resize to 200x200
            img = img.resize((200, 200))
            img.save(save_path, format='JPEG', quality=90)
        except Exception:
            # 画像として開けない場合は削除してエラー
            try:
                if os.path.exists(save_path):
                    os.remove(save_path)
            except Exception:
                pass
            flash('画像を読み込めませんでした')
            return redirect(url_for('profile', username=user['username']))
    except Exception:
        flash('画像の保存に失敗しました')
        return redirect(url_for('profile', username=user['username']))
    db = get_db()
    # remove old avatar if exists
    old = db.execute('SELECT avatar FROM users WHERE id = ?', (user['id'],)).fetchone()
    if old and old['avatar']:
        try:
            op = os.path.join(AVATAR_DIR, old['avatar'])
            if os.path.exists(op):
                os.remove(op)
        except Exception:
            pass
    db.execute('UPDATE users SET avatar = ? WHERE id = ?', (basename, user['id']))
    db.commit()
    flash('アイコンを更新しました')
    return redirect(url_for('profile', username=user['username']))

if __name__ == '__main__':
    host = os.environ.get('SNS_HOST', '0.0.0.0')
    try:
        port = int(os.environ.get('SNS_PORT', '5000'))
    except ValueError:
        port = 5000
    debug = os.environ.get('SNS_DEBUG', '1') != '0'
    app.run(host=host, port=port, debug=debug)
