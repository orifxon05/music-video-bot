"""Bot konfiguratsiyasi"""
import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Admin ID
ADMIN_ID = int(os.getenv("ADMIN_ID", "7693191223"))

# Database URL (Render/Koyeb)
DATABASE_URL = os.getenv("DATABASE_URL")

# Webhook sozlamalari
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")  # Masalan: https://your-bot.onrender.com
PORT = int(os.getenv("PORT", "8080"))
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "savemuzik-bot-secret-key-2026")

# Supported platforms
SUPPORTED_PLATFORMS = {
    "instagram": ["instagram.com", "instagr.am"],
    "tiktok": ["tiktok.com", "vm.tiktok.com", "vt.tiktok.com"],
    "facebook": ["facebook.com", "fb.watch", "fb.com"],
    "youtube": ["youtube.com", "youtu.be", "youtube.com/shorts"],
    "twitter": ["twitter.com", "x.com"],
    "pinterest": ["pinterest.com", "pin.it"],
    "reddit": ["reddit.com", "v.redd.it"],
}

# Download settings
MAX_FILE_SIZE_MB = 50  # Maximum file size in MB
DOWNLOAD_PATH = "downloads"

# Instagram sozlamalari (login yoki cookies kerak)
# 1-usul: Cookie fayli (eng yaxshi) - Browser'dan cookie eksport qiling
INSTAGRAM_COOKIES_FILE = os.getenv("INSTAGRAM_COOKIES_FILE", "www.instagram.com_cookies.txt")

# 2-usul: Login ma'lumotlari (kamroq tavsiya etiladi)
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME", "")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD", "")

# Proxy va Tashqi API (Fix 403 Forbidden)
# Railway'da uzoq muddat ishlash uchun proxy kerak
PROXY_URL = os.getenv("PROXY_URL", "") # Masalan: http://user:pass@host:port
COBALT_API = os.getenv("COBALT_API", "https://api.cobalt.tools/api/json")
COBALT_ENABLED = os.getenv("COBALT_ENABLED", "True").lower() == "true"

# Messages
MESSAGES = {
    "start": """╔══════════════════════════════╗
       🎵 **MUSIQA BOT** 🎵
╚══════════════════════════════╝

Assalomu alaykum! Men sizga yordam beraman:

📥 **YUKLAB OLISH**
└ Instagram, TikTok, YouTube linkini yuboring

🔍 **QO'SHIQ QIDIRISH**
└ Qo'shiq nomini yozing: `Sayidat Qaldi`

🎤 **MUSIQA ANIQLASH**
└ Audio/Voice yuboring - Shazam orqali topaman

🔄 **REMIX TOPISH**
└ Asl qo'shiqdan remix/cover versiyalarini topaman

━━━━━━━━━━━━━━━━━━━━━━━━

� **Qo'llab-quvvatlash:**
Instagram • TikTok • YouTube • Facebook • Twitter

⚡ Tez va Bepul!

Boshlash uchun link yoki qo'shiq nomi yuboring 👇""",

    "help": """📖 **YORDAM**

🔹 **Video yuklab olish:**
   Link yuboring va Video/Audio tugmasini tanlang

🔹 **Qo'shiq qidirish:**
   Qo'shiq nomini yozing, masalan:
   `Akon - Lonely`
   `Senorita`

🔹 **Musiqa aniqlash (Shazam):**
   Audio fayl yoki voice yuboring

🔹 **Remix/Cover:**
   Musiqa topilgandan so'ng tugmani bosing

━━━━━━━━━━━━━━━━━━━━━━━━

📱 **Platformalar:**
📸 Instagram  🎵 TikTok  📘 Facebook
▶️ YouTube   🐦 Twitter  📌 Pinterest

❓ Savollar: @admin""",

    "processing": "⏳ Kuting...",
    "downloading": "📥 Yuklanmoqda... ⚡",
    "recognizing": "🎵 Shazam aniqlamoqda...",
    "finding_remixes": "🔄 Remix/Cover qidirilmoqda...",
    "searching": "🔍 Qidirilmoqda...",
    "error": "❌ Xatolik! Qaytadan urinib ko'ring.",
    "unsupported_link": "❌ Bu platform qo'llab-quvvatlanmaydi.\n\n✅ Instagram, TikTok, YouTube, Facebook ishlaydi!",
    "no_music_found": "😔 Musiqa topilmadi. Boshqa audio sinab ko'ring.",
    "file_too_large": "📦 Fayl katta! Faqat audio yuboriladi...",
}
