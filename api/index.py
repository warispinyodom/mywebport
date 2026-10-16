import os
import json
import uuid
import secrets
import functools
import requests
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
import firebase_admin
from firebase_admin import credentials, db
from dotenv import load_dotenv

# โหลด Environment Variables ทั้งจาก .env และ .env.local
load_dotenv()
load_dotenv('.env.local')

app = Flask(__name__, template_folder='../templates', static_folder='../static')

# --- OWASP SESSION SECURITY CONFIGURATION ---
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'my-portfolio-static-production-secret-key-2026-v1')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)

DATABASE_URL = os.getenv('FIREBASE_DATABASE_URL', 'https://mythical-envoy-510318-t9-default-rtdb.asia-southeast1.firebasedatabase.app')

FAILED_ATTEMPTS = {}

# --- HELPER PARSE JSON FROM ENV VARS SAFELY ---
def parse_env_json(env_var_name):
    raw_val = os.getenv(env_var_name)
    if not raw_val:
        return None
    try:
        cleaned = raw_val.strip().strip("'\"")
        cred_dict = json.loads(cleaned)
        if isinstance(cred_dict, dict) and 'private_key' in cred_dict:
            cred_dict['private_key'] = cred_dict['private_key'].replace('\\n', '\n')
        return cred_dict
    except Exception as e:
        print(f"❌ Error parsing env [{env_var_name}]: {e}")
        return None

# --- OWASP SECURITY HEADERS ---
@app.after_request
def add_security_headers(response):
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response

# --- OWASP ANTI-CSRF TOKEN SYSTEM ---
def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']

app.jinja_env.globals['csrf_token'] = generate_csrf_token

def verify_csrf():
    if request.method in ['POST', 'PUT', 'DELETE']:
        token = session.get('_csrf_token')
        form_token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
        
        if not token and form_token:
            session['_csrf_token'] = form_token
            token = form_token

        if not token or not form_token or token != form_token:
            flash('🔒 คำขอไม่ถูกต้องหรือหมดอายุ (CSRF Validation Failed)', 'danger')
            return False
    return True

# --- SAFE FIREBASE REALTIME DATABASE INIT ---
def init_firebase():
    if not firebase_admin._apps:
        config = {'databaseURL': DATABASE_URL}
        cred = None

        for env_key in ['FIREBASE_CREDENTIALS', 'FIREBASE_KEY', 'FIREBASE_SERVICE_ACCOUNT']:
            cred_dict = parse_env_json(env_key)
            if cred_dict:
                cred = credentials.Certificate(cred_dict)
                break

        if not cred:
            for local_file in ['serviceAccountKey.json', 'firebaseKey.json', 'firebase_key.json', 'mythical-envoy-510318-t9-firebase-adminsdk-fbsvc-604ed12749.json']:
                if os.path.exists(local_file):
                    try:
                        cred = credentials.Certificate(local_file)
                        break
                    except Exception:
                        continue

        if cred:
            firebase_admin.initialize_app(cred, config)
            print("✅ Firebase Admin initialized successfully")
        else:
            print("⚠️ Warning: Firebase credentials not found during startup!")

# เรียกใช้งานแบบ Safe Init ตอนบูตระบบ
try:
    init_firebase()
except Exception as e:
    print(f"❌ Firebase startup exception: {e}")

# --- SUPABASE STORAGE HELPER ---
def upload_image_to_storage(file_obj, folder='projects'):
    if not file_obj or file_obj.filename == '':
        return None, "ไม่ได้เลือกไฟล์รูปภาพ"
        
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY')
    bucket_name = os.getenv('SUPABASE_BUCKET', 'portfolio-images')

    if not supabase_url or not supabase_key:
        return None, "ไม่พบ SUPABASE_URL หรือ SUPABASE_KEY ใน Environment Variables"

    try:
        ext = os.path.splitext(file_obj.filename)[1].lower()
        if not ext or ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg']:
            ext = '.jpg'
            
        unique_filename = f"{folder}/{uuid.uuid4().hex}{ext}"
        file_bytes = file_obj.read()
        mimetype = file_obj.mimetype or 'image/jpeg'

        clean_url = supabase_url.strip().rstrip('/')
        clean_key = supabase_key.strip().strip("'\"")
        clean_bucket = bucket_name.strip().strip("'\"")

        upload_endpoint = f"{clean_url}/storage/v1/object/{clean_bucket}/{unique_filename}"
        
        headers = {
            "Authorization": f"Bearer {clean_key}",
            "apiKey": clean_key,
            "Content-Type": mimetype
        }

        response = requests.post(upload_endpoint, data=file_bytes, headers=headers, timeout=15)

        if response.status_code in [200, 201]:
            public_url = f"{clean_url}/storage/v1/object/public/{clean_bucket}/{unique_filename}"
            return public_url, None
        else:
            err_info = response.json() if response.text else response.text
            return None, f"Supabase Error ({response.status_code}): {err_info}"

    except Exception as e:
        print(f"❌ Supabase Upload Exception: {e}")
        return None, str(e)

@app.context_processor
def inject_profile():
    default_profile = {
        'name': 'Waris Pinyodom',
        'title': 'Cyber Security / Full Stack Developer',
        'bio': 'มุ่งมั่นพัฒนาเว็บแอปพลิเคชันที่มีคุณภาพ ปรับแต่งได้ตามโจทย์ และใช้งานง่าย',
        'skills': ['Python', 'Flask', 'JavaScript', 'Firebase', 'Tailwind CSS', 'Supabase'],
        'github': 'https://github.com/warispinyodom/',
        'linkedin': 'https://linkedin.com',
        'email': 'waris.pi@kkumail.com',
        'avatar_url': ''
    }
    try:
        if not firebase_admin._apps:
            init_firebase()
        profile_db = db.reference('profile').get()
        profile = {**default_profile, **profile_db} if isinstance(profile_db, dict) else default_profile
    except Exception:
        profile = default_profile
    return dict(profile=profile)

def admin_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            flash('กรุณาเข้าสู่ระบบในฐานะ Admin ก่อนใช้งาน', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- PUBLIC ROUTES ---
@app.route('/')
def home():
    projects = []
    try:
        if not firebase_admin._apps:
            init_firebase()
        data = db.reference('projects').get()
        if isinstance(data, dict):
            for key, val in data.items():
                val['id'] = key
                projects.append(val)
            projects.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    except Exception as e:
        print(f"Error fetching projects: {e}")
    return render_template('index.html', projects=projects)

@app.route('/contact', methods=['POST'])
def contact():
    if not verify_csrf():
        return redirect(url_for('home') + '#contact')

    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    subject = request.form.get('subject', '').strip()
    message = request.form.get('message', '').strip()

    if not name or not email or not message:
        flash('กรุณากรอกข้อมูลให้ครบถ้วน', 'danger')
        return redirect(url_for('home') + '#contact')

    try:
        if not firebase_admin._apps:
            init_firebase()
        db.reference('messages').push({
            'name': name,
            'email': email,
            'subject': subject or 'สอบถามเพิ่มเติม',
            'message': message,
            'is_read': False,
            'created_at': datetime.utcnow().isoformat()
        })
        flash('ส่งข้อความเรียบร้อยแล้ว ขอบคุณที่ติดต่อมาครับ!', 'success')
    except Exception as e:
        flash(f'เกิดข้อผิดพลาดในการบันทึกข้อความ: {e}', 'danger')

    return redirect(url_for('home') + '#contact')

# --- AUTHENTICATION ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        if not verify_csrf():
            return redirect(url_for('login'))

        client_ip = request.remote_addr or '127.0.0.1'
        now = datetime.utcnow()

        ip_attempts = FAILED_ATTEMPTS.get(client_ip, {'count': 0, 'lockout_until': None})
        if ip_attempts['lockout_until'] and now < ip_attempts['lockout_until']:
            remaining = int((ip_attempts['lockout_until'] - now).total_seconds() / 60) + 1
            flash(f'⚠️ พยายามเข้าสู่ระบบผิดพลาดเกินกำหนด กรุณาลองใหม่ในอีก {remaining} นาที', 'danger')
            return render_template('login.html')

        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        authenticated = False

        try:
            if not firebase_admin._apps:
                init_firebase()
            admin_data = db.reference('admin').get()
            if isinstance(admin_data, dict):
                db_user = admin_data.get('username')
                db_hash = admin_data.get('password_hash')
                db_plain = admin_data.get('password')

                if username == db_user:
                    if db_hash:
                        if isinstance(db_hash, str) and db_hash.startswith(('scrypt:', 'pbkdf2:', 'argon2:')):
                            if check_password_hash(db_hash, password):
                                authenticated = True
                        elif db_hash == password:
                            authenticated = True
                            new_hash = generate_password_hash(password, method='scrypt')
                            db.reference('admin').update({'password_hash': new_hash})

                    if not authenticated and db_plain and db_plain == password:
                        authenticated = True
                        new_hash = generate_password_hash(password, method='scrypt')
                        db.reference('admin').update({
                            'password_hash': new_hash,
                            'password': None
                        })
        except Exception as e:
            print(f"Error authenticating admin: {e}")

        if not authenticated:
            env_user = os.getenv('ADMIN_USERNAME', 'admin')
            env_pass = os.getenv('ADMIN_PASSWORD', 'admin123')
            if username == env_user and password == env_pass:
                authenticated = True

        if authenticated:
            FAILED_ATTEMPTS.pop(client_ip, None)

            session.clear()
            session.permanent = True
            session['is_admin'] = True
            session['_csrf_token'] = secrets.token_hex(32)

            flash('เข้าสู่ระบบสำเร็จ!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            ip_attempts['count'] += 1
            if ip_attempts['count'] >= 5:
                ip_attempts['lockout_until'] = now + timedelta(minutes=15)
                flash('⚠️ พยายามเข้าสู่ระบบผิดพลาดเกิน 5 ครั้ง! ระบบถูกระงับชั่วคราว 15 นาที', 'danger')
            else:
                flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง', 'danger')

            FAILED_ATTEMPTS[client_ip] = ip_attempts

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('ออกจากระบบเรียบร้อยแล้ว', 'info')
    return redirect(url_for('home'))

# --- ADMIN ROUTES ---
@app.route('/admin')
@admin_required
def admin_dashboard():
    projects = []
    messages = []
    profile = {}
    
    try:
        if not firebase_admin._apps:
            init_firebase()
        projects_dict = db.reference('projects').get() or {}
        projects = [{'id': k, **v} for k, v in projects_dict.items()] if isinstance(projects_dict, dict) else []
        projects.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        messages_dict = db.reference('messages').get() or {}
        messages = [{'id': k, **v} for k, v in messages_dict.items()] if isinstance(messages_dict, dict) else []
        messages.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        profile = db.reference('profile').get() or {}
    except Exception as e:
        print(f"Error fetching dashboard data: {e}")

    return render_template('admin/dashboard.html', projects=projects, messages=messages, profile=profile)

@app.route('/admin/profile', methods=['GET', 'POST'])
@admin_required
def edit_profile():
    if not firebase_admin._apps:
        init_firebase()
    ref = db.reference('profile')
    current_profile = ref.get() or {}

    if request.method == 'POST':
        if not verify_csrf():
            return redirect(url_for('edit_profile'))

        avatar_url = current_profile.get('avatar_url', '') if isinstance(current_profile, dict) else ''
        file = request.files.get('avatar_file')
        upload_err = None
        
        if file and file.filename != '':
            new_avatar, upload_err = upload_image_to_storage(file, folder='avatars')
            if new_avatar:
                avatar_url = new_avatar
        elif request.form.get('avatar_url'):
            avatar_url = request.form.get('avatar_url').strip()

        skills = [s.strip() for s in request.form.get('skills', '').split(',') if s.strip()]

        ref.set({
            'name': request.form.get('name', '').strip(),
            'title': request.form.get('title', '').strip(),
            'bio': request.form.get('bio', '').strip(),
            'skills': skills,
            'github': request.form.get('github', '').strip(),
            'linkedin': request.form.get('linkedin', '').strip(),
            'email': request.form.get('email', '').strip(),
            'avatar_url': avatar_url,
            'updated_at': datetime.utcnow().isoformat()
        })

        if upload_err:
            flash(f'⚠️ บันทึกข้อความส่วนตัวแล้ว แต่ไม่สามารถอัปโหลดรูปภาพได้: {upload_err}', 'warning')
        else:
            flash('อัปเดตข้อมูลส่วนตัวเรียบร้อยแล้ว!', 'success')

        return redirect(url_for('admin_dashboard'))

    if isinstance(current_profile, dict):
        current_profile['skills_str'] = ', '.join(current_profile.get('skills', []))
    else:
        current_profile = {'skills_str': ''}

    return render_template('admin/profile_form.html', profile=current_profile)

@app.route('/admin/project/add', methods=['GET', 'POST'])
@admin_required
def add_project():
    if request.method == 'POST':
        if not verify_csrf():
            return redirect(url_for('add_project'))

        image_url = None
        upload_err = None
        file = request.files.get('image_file')
        
        if file and file.filename != '':
            image_url, upload_err = upload_image_to_storage(file, folder='projects')

        if not image_url:
            image_url = request.form.get('image_url', '').strip() or 'https://via.placeholder.com/600x400?text=No+Image'

        tags = [t.strip() for t in request.form.get('tags', '').split(',') if t.strip()]
        
        if not firebase_admin._apps:
            init_firebase()
        db.reference('projects').push({
            'title': request.form.get('title', '').strip(),
            'category': request.form.get('category', 'Web App').strip(),
            'description': request.form.get('description', '').strip(),
            'image_url': image_url,
            'demo_url': request.form.get('demo_url', '').strip(),
            'github_url': request.form.get('github_url', '').strip(),
            'tags': tags,
            'is_featured': 'is_featured' in request.form,
            'created_at': datetime.utcnow().isoformat()
        })

        if upload_err:
            flash(f'⚠️ เพิ่มผลงานสำเร็จ แต่การอัปโหลดรูปภาพล้มเหลว: {upload_err}', 'warning')
        else:
            flash('เพิ่มผลงานเรียบร้อยแล้ว', 'success')

        return redirect(url_for('admin_dashboard'))

    return render_template('admin/project_form.html', project=None, title="เพิ่มผลงานใหม่")

@app.route('/admin/project/edit/<project_id>', methods=['GET', 'POST'])
@admin_required
def edit_project(project_id):
    if not firebase_admin._apps:
        init_firebase()
    ref = db.reference(f'projects/{project_id}')
    project = ref.get()

    if not project:
        flash('ไม่พบผลงานนี้ในระบบ', 'danger')
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        if not verify_csrf():
            return redirect(url_for('edit_project', project_id=project_id))

        image_url = project.get('image_url')
        upload_err = None
        file = request.files.get('image_file')
        
        if file and file.filename != '':
            new_image_url, upload_err = upload_image_to_storage(file, folder='projects')
            if new_image_url:
                image_url = new_image_url
        elif request.form.get('image_url'):
            image_url = request.form.get('image_url').strip()

        tags = [t.strip() for t in request.form.get('tags', '').split(',') if t.strip()]
        ref.update({
            'title': request.form.get('title', '').strip(),
            'category': request.form.get('category', '').strip(),
            'description': request.form.get('description', '').strip(),
            'image_url': image_url,
            'demo_url': request.form.get('demo_url', '').strip(),
            'github_url': request.form.get('github_url', '').strip(),
            'tags': tags,
            'is_featured': 'is_featured' in request.form
        })

        if upload_err:
            flash(f'⚠️ อัปเดตข้อมูลผลงานแล้ว แต่การอัปโหลดรูปภาพล้มเหลว: {upload_err}', 'warning')
        else:
            flash('อัปเดตผลงานเรียบร้อยแล้ว', 'success')

        return redirect(url_for('admin_dashboard'))

    project['id'] = project_id
    project['tags_str'] = ', '.join(project.get('tags', []))
    return render_template('admin/project_form.html', project=project, title="แก้ไขผลงาน")

@app.route('/admin/project/delete/<project_id>', methods=['POST'])
@admin_required
def delete_project(project_id):
    if verify_csrf():
        if not firebase_admin._apps:
            init_firebase()
        db.reference(f'projects/{project_id}').delete()
        flash('ลบผลงานเรียบร้อยแล้ว', 'info')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/message/read/<msg_id>', methods=['POST'])
@admin_required
def mark_message_read(msg_id):
    if verify_csrf():
        if not firebase_admin._apps:
            init_firebase()
        db.reference(f'messages/{msg_id}').update({'is_read': True})
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/message/delete/<msg_id>', methods=['POST'])
@admin_required
def delete_message(msg_id):
    if verify_csrf():
        if not firebase_admin._apps:
            init_firebase()
        db.reference(f'messages/{msg_id}').delete()
        flash('ลบข้อความเรียบร้อยแล้ว', 'info')
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)