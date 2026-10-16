import os
import firebase_admin
from firebase_admin import credentials, db

# 1. โหลดคีย์ Service Account JSON ในโปรเจกต์
json_key_path = "mythical-envoy-510318-t9-firebase-adminsdk-fbsvc-604ed12749.json"
database_url = "https://mythical-envoy-510318-t9-default-rtdb.asia-southeast1.firebasedatabase.app"

if not os.path.exists(json_key_path):
    print(f"❌ ไม่พบไฟล์ {json_key_path} ในโฟลเดอร์โปรเจกต์")
    exit()

cred = credentials.Certificate(json_key_path)
firebase_admin.initialize_app(cred, {'databaseURL': database_url})

# 2. ชุดข้อมูลเริ่มต้นที่ตรงตามระบบหลังบ้าน
initial_data = {
    "admin": {
        "username": "admin",
        "password": "admin123"
    },
    "profile": {
        "name": "Waris Pinyodom",
        "title": "Cyber Security / Full Stack Developer",
        "bio": "มุ่งมั่นพัฒนาเว็บแอปพลิเคชันที่มีคุณภาพ ปรับแต่งได้ตามโจทย์ และใช้งานง่าย",
        "skills": ["Python", "Flask", "JavaScript", "Firebase", "Tailwind CSS", "Supabase"],
        "email": "waris.pi@kkumail.com",
        "github": "https://github.com/warispinyodom/",
        "linkedin": "https://linkedin.com",
        "avatar_url": ""
    }
}

# 3. อัปเดตข้อมูลเข้าฐานข้อมูลโดยตรง
db.reference('/').update(initial_data)
print("✅ นำเข้าข้อมูล admin และ profile เข้า Firebase Realtime Database สำเร็จเรียบร้อย!")