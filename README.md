# 🎵 Musiqa & Video Bot

Instagram, TikTok, Facebook va boshqa platformalardan video yuklab olish, musiqa aniqlash (Shazam) va remix/cover topish boti.

## 🚀 Xususiyatlar

- **📥 Video yuklab olish** - Instagram, TikTok, Facebook, YouTube va boshqa platformalardan
- **🎵 Musiqa aniqlash** - Shazam API orqali audio'dan qo'shiqni topish
- **🎧 Audio ajratish** - Video'dan audio chiqarib olish
- **🔄 Remix/Cover topish** - YouTube'dan remix va cover versiyalarini qidirish

## 📋 Qo'llab-quvvatlanadigan platformalar

| Platform | Status |
|----------|--------|
| Instagram (Reels, Posts) | ✅ |
| TikTok | ✅ |
| Facebook | ✅ |
| YouTube / YouTube Shorts | ✅ |
| Twitter/X | ✅ |
| Pinterest | ✅ |
| Reddit | ✅ |

## 🛠 O'rnatish

### 1. Talablar

- Python 3.10+
- FFmpeg (audio convert uchun)

### 2. FFmpeg o'rnatish

**Windows:**
```bash
# Chocolatey orqali
choco install ffmpeg

# Yoki winget orqali
winget install FFmpeg
```

**Linux:**
```bash
sudo apt install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

### 3. Loyihani sozlash

```bash
# Virtual environment yaratish
python -m venv venv

# Aktivatsiya qilish
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Kutubxonalarni o'rnatish
pip install -r requirements.txt
```

### 4. Environment Variables

`.env.example` faylini `.env` ga nusxalang va sozlang:

```bash
cp .env.example .env
```

`.env` faylini tahrirlang:
```env
BOT_TOKEN=your_telegram_bot_token_here
ADMIN_ID=your_telegram_id_here
```

### 5. Botni ishga tushirish

```bash
python bot.py
```

## 🤖 Bot buyruqlari

| Buyruq | Tavsif |
|--------|--------|
| `/start` | Botni boshlash |
| `/help` | Yordam olish |
| `/stats` | Statistika ko'rish |

## 📱 Foydalanish

1. **Video yuklab olish:**
   - Instagram, TikTok yoki boshqa platformadan link yuboring
   - Bot video va audio'ni yuklab beradi

2. **Musiqa aniqlash:**
   - Audio fayl yuboring (voice, mp3, va h.k.)
   - Bot Shazam orqali qo'shiqni aniqlaydi

3. **Remix/Cover topish:**
   - Musiqa aniqlanganidan so'ng "Remix/Cover" tugmasini bosing
   - Bot YouTube'dan versiyalarni topib beradi

## 📁 Loyiha strukturasi

```
new/
├── bot.py              # Asosiy bot fayli
├── config.py           # Konfiguratsiya
├── downloader.py       # Video/Audio yuklab olish
├── music_recognizer.py # Shazam integratsiyasi
├── remix_finder.py     # Remix/Cover qidirish
├── requirements.txt    # Kutubxonalar
├── .env               # Environment variables
└── README.md          # Dokumentatsiya
```

## ⚠️ Eslatmalar

- Maksimal fayl hajmi: 50MB
- Telegram bot fayl chegarasi tufayli katta videolar yuborilmasligi mumkin
- FFmpeg o'rnatilgan bo'lishi kerak

## 📄 Litsenziya

MIT License

## 👤 Muallif

Telegram: @admin
