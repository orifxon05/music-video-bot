"""Bot konfiguratsiyasi"""
import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Admin ID
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

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

# Messages
MESSAGES = {
    "start": """🎵 **Musiqa & Video Bot**ga xush kelibsiz!

🎬 **Video yuklab olish:**
Instagram, TikTok, Facebook, YouTube va boshqa platformalardan link yuboring.

🎵 **Musiqa topish (Shazam):**
Audio fayl yuboring - men qo'shiq nomini topaman!

🔄 **Remix/Cover topish:**
Video yoki audio yuboring - men remix va cover versiyalarini topaman!

📋 **Buyruqlar:**
/start - Botni boshlash
/help - Yordam
/stats - Statistika

Endi link yoki audio yuboring! 👇""",

    "help": """📖 **Yordam**

**Video yuklab olish:**
• Instagram, TikTok, Facebook, YouTube havolalarini yuboring
• Bot video va audio'ni yuklab beradi

**Musiqa aniqlash:**
• Audio fayl yuboring (voice, mp3, va h.k.)
• Bot Shazam orqali qo'shiqni aniqlaydi

**Remix/Cover topish:**
• Video yoki audio'dagi musiqa aniqlanganidan so'ng
• Bot YouTube'dan remix/cover versiyalarini topadi

**Qo'llab-quvvatlanadigan platformalar:**
📸 Instagram (Reels, Posts, Stories)
🎵 TikTok
📘 Facebook
▶️ YouTube / YouTube Shorts
🐦 Twitter/X
📌 Pinterest
🔴 Reddit

❓ Savollar uchun: @admin""",

    "processing": "⏳ Qayta ishlanmoqda...",
    "downloading": "📥 Yuklab olinmoqda...",
    "recognizing": "🎵 Musiqa aniqlanmoqda...",
    "finding_remixes": "🔄 Remix/Cover qidirilmoqda...",
    "error": "❌ Xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.",
    "unsupported_link": "❌ Bu platforma qo'llab-quvvatlanmaydi.",
    "no_music_found": "😔 Musiqa topilmadi. Boshqa audio bilan sinab ko'ring.",
    "file_too_large": "❌ Fayl juda katta (max 50MB).",
}
