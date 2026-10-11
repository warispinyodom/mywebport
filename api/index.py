import os
import json
import uuid
import functools
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
import firebase_admin
from firebase_admin import credentials, db, storage
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, template_folder='../templates', static_folder='../static')
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'default-dev-secret-key')

# URL และ Storage Bucket
DATABASE_URL = os.getenv('FIREBASE_DATABASE_URL', 'https://fluke-cyberport-default-rtdb.asia-southeast1.firebasedatabase.app')
STORAGE_BUCKET = os.getenv('FIREBASE_STORAGE_BUCKET', 'fluke-cyberport.firebasestorage.app')

# --- เชื่อมต่อ Firebase ---
def init_firebase():
    if not firebase_admin._apps:
        local_key_path = 'serviceAccountKey.json'
        config = {
            'databaseURL': DATABASE_URL,
            'storageBucket': STORAGE_BUCKET
        }
        
        if os.path.exists(local_key_path):
            cred = credentials.Certificate(local_key_path)
            firebase_admin.initialize_app(cred, config)
            print("🟢 Firebase: เชื่อมต่อ Realtime Database & Storage ผ่าน serviceAccountKey.json")
        else:
            cred_json = os.getenv('FIREBASE_CREDENTIALS')
            if cred_json:
                cred_dict = json.loads(cred_json)
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred, config)
                print("☁️ Firebase: เชื่อมต่อผ่าน Vercel Environment Variable")
            else:
                raise RuntimeError("❌ ไม่พบสิทธิ์การเชื่อมต่อ Firebase!")

init_firebase()

# --- ส่งตัวแปร profile ให้กับทุกๆ หน้า Template อัตโนมัติ ---
@app.context_processor
def inject_profile():
    default_profile = {
        'name': 'ชื่อ-นามสกุลของคุณ',
        'title': 'Full Stack Developer / Software Engineer',
        'bio': 'มุ่งมั่นพัฒนาเว็บแอปพลิเคชันที่มีคุณภาพ ปรับแต่งได้ตามโจทย์ และใช้งานง่าย',
        'skills': ['Python', 'Flask', 'JavaScript', 'Tailwind CSS', 'Firebase', 'Docker', 'Git'],
        'github': 'https://github.com',
        'linkedin': 'https://linkedin.com',
        'email': 'your.email@example.com',
        'avatar_url': ''
    }
    try:
        profile_db = db.reference('profile').get()
        if profile_db and isinstance(profile_db, dict):
            profile = {**default_profile, **profile_db}
        else:
            profile = default_profile
    except Exception as e:
        print(f"Context Processor Profile Error: {e}")
        profile = default_profile

    return dict(profile=profile)

# --- ฟังก์ชันอัปโหลดรูปภาพเข้า Firebase Storage ---
def upload_image_to_storage(file_obj, folder='projects'):
    if not file_obj or file_obj.filename == '':
        return None
    try:
        filename = secure_filename(file_obj.filename)
        unique_name = f"{folder}/{uuid.uuid4().hex}_{filename}"
        
        bucket = storage.bucket()
        blob = bucket.blob(unique_name)
        blob.upload_from_string(
            file_obj.read(),
            content_type=file_obj.content_type
        )
        blob.make_public()
        return blob.public_url
    except Exception as e:
        print(f"Error uploading image to Firebase Storage: {e}")
        return None

# --- Admin Authentication Decorator ---
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
        ref = db.reference('projects')
        data = ref.get()
        if data and isinstance(data, dict):
            for key, val in data.items():
                val['id'] = key
                projects.append(val)
            projects.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    except Exception as e:
        print(f"Error fetching projects: {e}")

    # ดึงข้อมูลประวัติจาก Firebase (โหนด profile)
    default_profile = {
        'name': 'ชื่อ-นามสกุลของคุณ',
        'title': 'Full Stack Developer / Software Engineer',
        'bio': 'มุ่งมั่นพัฒนาเว็บแอปพลิเคชันที่มีคุณภาพ ปรับแต่งได้ตามโจทย์ และใช้งานง่าย',
        'skills': ['Python', 'Flask', 'JavaScript', 'Tailwind CSS', 'Firebase', 'Docker', 'Git'],
        'github': 'https://github.com',
        'linkedin': 'https://linkedin.com',
        'email': 'your.email@example.com',
        'avatar_url': ''
    }
    try:
        profile_db = db.reference('profile').get()
        if profile_db and isinstance(profile_db, dict):
            profile = {**default_profile, **profile_db}
        else:
            profile = default_profile
    except Exception as e:
        print(f"Error fetching profile: {e}")
        profile = default_profile

    return render_template('index.html', projects=projects, profile=profile)

@app.route('/contact', methods=['POST'])
def contact():
    name = request.form.get('name')
    email = request.form.get('email')
    subject = request.form.get('subject')
    message = request.form.get('message')

    if not name or not email or not message:
        flash('กรุณากรอกข้อมูลให้ครบถ้วน', 'danger')
        return redirect(url_for('home') + '#contact')

    db.reference('messages').push({
        'name': name,
        'email': email,
        'subject': subject or 'สอบถามเพิ่มเติม',
        'message': message,
        'is_read': False,
        'created_at': datetime.utcnow().isoformat()
    })
    flash('ส่งข้อความเรียบร้อยแล้ว ขอบคุณที่ติดต่อมาครับ!', 'success')
    return redirect(url_for('home') + '#contact')

# --- AUTHENTICATION ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        try:
            admin_data = db.reference('admin').get()
            if admin_data and isinstance(admin_data, dict):
                if username == admin_data.get('username') and password == admin_data.get('password'):
                    session['is_admin'] = True
                    flash('เข้าสู่ระบบสำเร็จ!', 'success')
                    return redirect(url_for('admin_dashboard'))
        except Exception as e:
            print(f"Error fetching admin: {e}")

        admin_user = os.getenv('ADMIN_USERNAME', 'admin')
        admin_pass = os.getenv('ADMIN_PASSWORD', 'admin123')

        if username == admin_user and password == admin_pass:
            session['is_admin'] = True
            flash('เข้าสู่ระบบสำเร็จ!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง', 'danger')

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
    projects_dict = db.reference('projects').get() or {}
    projects = []
    if isinstance(projects_dict, dict):
        for k, v in projects_dict.items():
            v['id'] = k
            projects.append(v)
        projects.sort(key=lambda x: x.get('created_at', ''), reverse=True)

    messages_dict = db.reference('messages').get() or {}
    messages = []
    if isinstance(messages_dict, dict):
        for k, v in messages_dict.items():
            v['id'] = k
            messages.append(v)
        messages.sort(key=lambda x: x.get('created_at', ''), reverse=True)

    profile = db.reference('profile').get() or {}

    return render_template('admin/dashboard.html', projects=projects, messages=messages, profile=profile)

# --- ADMIN: จัดการข้อมูลส่วนตัว (Edit Profile) ---
@app.route('/admin/profile', methods=['GET', 'POST'])
@admin_required
def edit_profile():
    ref = db.reference('profile')
    current_profile = ref.get() or {}

    if request.method == 'POST':
        avatar_url = current_profile.get('avatar_url', '') if isinstance(current_profile, dict) else ''
        file = request.files.get('avatar_file')
        
        if file and file.filename != '':
            new_avatar = upload_image_to_storage(file, folder='avatars')
            if new_avatar:
                avatar_url = new_avatar
        elif request.form.get('avatar_url'):
            avatar_url = request.form.get('avatar_url')

        skills = [s.strip() for s in request.form.get('skills', '').split(',') if s.strip()]

        updated_data = {
            'name': request.form.get('name', ''),
            'title': request.form.get('title', ''),
            'bio': request.form.get('bio', ''),
            'skills': skills,
            'github': request.form.get('github', ''),
            'linkedin': request.form.get('linkedin', ''),
            'email': request.form.get('email', ''),
            'avatar_url': avatar_url,
            'updated_at': datetime.utcnow().isoformat()
        }
        ref.set(updated_data)
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
        image_url = None
        file = request.files.get('image_file')
        if file and file.filename != '':
            image_url = upload_image_to_storage(file, folder='projects')

        if not image_url:
            image_url = request.form.get('image_url') or 'https://via.placeholder.com/600x400?text=No+Image'

        tags = [t.strip() for t in request.form.get('tags', '').split(',') if t.strip()]
        db.reference('projects').push({
            'title': request.form.get('title'),
            'category': request.form.get('category', 'Web App'),
            'description': request.form.get('description'),
            'image_url': image_url,
            'demo_url': request.form.get('demo_url'),
            'github_url': request.form.get('github_url'),
            'tags': tags,
            'is_featured': 'is_featured' in request.form,
            'created_at': datetime.utcnow().isoformat()
        })
        flash('เพิ่มผลงานเรียบร้อยแล้ว', 'success')
        return redirect(url_for('admin_dashboard'))

    return render_template('admin/project_form.html', project=None, title="เพิ่มผลงานใหม่")

@app.route('/admin/project/edit/<project_id>', methods=['GET', 'POST'])
@admin_required
def edit_project(project_id):
    ref = db.reference(f'projects/{project_id}')
    project = ref.get()

    if not project:
        flash('ไม่พบผลงานนี้ในระบบ', 'danger')
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        image_url = project.get('image_url')
        file = request.files.get('image_file')
        
        if file and file.filename != '':
            new_image_url = upload_image_to_storage(file, folder='projects')
            if new_image_url:
                image_url = new_image_url
        elif request.form.get('image_url'):
            image_url = request.form.get('image_url')

        tags = [t.strip() for t in request.form.get('tags', '').split(',') if t.strip()]
        ref.update({
            'title': request.form.get('title'),
            'category': request.form.get('category'),
            'description': request.form.get('description'),
            'image_url': image_url,
            'demo_url': request.form.get('demo_url'),
            'github_url': request.form.get('github_url'),
            'tags': tags,
            'is_featured': 'is_featured' in request.form
        })
        flash('อัปเดตผลงานเรียบร้อยแล้ว', 'success')
        return redirect(url_for('admin_dashboard'))

    project['id'] = project_id
    project['tags_str'] = ', '.join(project.get('tags', []))
    return render_template('admin/project_form.html', project=project, title="แก้ไขผลงาน")

@app.route('/admin/project/delete/<project_id>', methods=['POST'])
@admin_required
def delete_project(project_id):
    db.reference(f'projects/{project_id}').delete()
    flash('ลบผลงานเรียบร้อยแล้ว', 'info')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/message/read/<msg_id>', methods=['POST'])
@admin_required
def mark_message_read(msg_id):
    db.reference(f'messages/{msg_id}').update({'is_read': True})
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/message/delete/<msg_id>', methods=['POST'])
@admin_required
def delete_message(msg_id):
    db.reference(f'messages/{msg_id}').delete()
    flash('ลบข้อความเรียบร้อยแล้ว', 'info')
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)