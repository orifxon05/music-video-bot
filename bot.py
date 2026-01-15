"""Asosiy Telegram Bot"""
import os
import re
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from telegram.constants import ParseMode, ChatAction

from config import BOT_TOKEN, MESSAGES, DOWNLOAD_PATH
from downloader import Downloader
from music_recognizer import MusicRecognizer
from remix_finder import RemixFinder
from music_searcher import MusicSearcher

# Logging sozlamalari
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Modullarni ishga tushirish
downloader = Downloader()
recognizer = MusicRecognizer()
remix_finder = RemixFinder()
searcher = MusicSearcher()

# Foydalanuvchi ma'lumotlarini saqlash
user_music_data = {}
user_search_data = {}  # Qidiruv natijalari


# ==================== HANDLERS ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start buyrug'i"""
    await update.message.reply_text(
        MESSAGES["start"],
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help buyrug'i"""
    await update.message.reply_text(
        MESSAGES["help"],
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Statistika buyrug'i"""
    # Oddiy statistika
    downloads_count = len(os.listdir(DOWNLOAD_PATH)) if os.path.exists(DOWNLOAD_PATH) else 0
    
    text = f"""📊 **Bot Statistikasi**

📥 Yuklab olingan fayllar: {downloads_count}
👥 Faol foydalanuvchilar: {len(user_music_data)}

🤖 Bot ishlayapti!"""
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str = None):
    """Link yuborilganda"""
    message = update.message
    user_id = message.from_user.id
    
    # URL ni olish
    if url is None:
        url = message.text.strip()
    
    # URL ni tekshirish
    if not downloader.is_supported_url(url):
        await message.reply_text(MESSAGES["unsupported_link"])
        return
    
    # Jarayonni boshlash
    status_msg = await message.reply_text(MESSAGES["downloading"])
    await context.bot.send_chat_action(message.chat_id, ChatAction.UPLOAD_VIDEO)
    
    try:
        # Video yuklab olish
        video_result = await downloader.download_video(url, user_id)
        
        video_sent = False
        video_path = None
        
        if video_result.get("success"):
            video_path = video_result["filepath"]
            
            # Fayl hajmini tekshirish (50MB dan kichik bo'lsa yuborish)
            import os
            file_size_mb = os.path.getsize(video_path) / (1024 * 1024)
            
            if file_size_mb <= 50:
                try:
                    # Video yuborish
                    await status_msg.edit_text("📤 Video yuborilmoqda...")
                    
                    video_title = video_result.get('title', 'Video')
                    platform = video_result.get('platform', 'Nomalum').title()
                    uploader = video_result.get('uploader', 'Nomalum')
                    duration = format_duration(video_result.get('duration', 0))
                    
                    caption = f"""🎬 **{video_title}**

📱 Platform: {platform}
👤 Muallif: {uploader}
⏱ Davomiylik: {duration}

🎵 Audio va remix topish uchun quyidagi tugmani bosing 👇"""
                    
                    keyboard = [
                        [
                            InlineKeyboardButton("🎵 Audio olish", callback_data=f"audio_{user_id}"),
                            InlineKeyboardButton("🔄 Remix/Cover", callback_data=f"remix_{user_id}"),
                        ]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    
                    with open(video_path, 'rb') as video_file:
                        await message.reply_video(
                            video=video_file,
                            caption=caption,
                            parse_mode=ParseMode.MARKDOWN,
                            reply_markup=reply_markup,
                        )
                    video_sent = True
                except Exception as video_error:
                    logger.warning(f"Video yuborishda xato: {video_error}")
            else:
                logger.info(f"Video juda katta: {file_size_mb:.1f}MB, faqat audio yuboriladi")
        
        # Agar video yuborilmagan bo'lsa, faqat audio yuborish
        if not video_sent:
            await status_msg.edit_text("🎵 Video katta, audio yuklanmoqda...")
            await context.bot.send_chat_action(message.chat_id, ChatAction.UPLOAD_AUDIO)
            
            audio_result = await downloader.download_audio(url, user_id)
            
            if audio_result.get("success"):
                audio_path = audio_result["filepath"]
                
                # Musiqani aniqlash
                music_result = await recognizer.recognize_from_file(audio_path)
                
                video_title = video_result.get('title', 'Audio') if video_result.get('success') else 'Audio'
                artist_name = music_result.get('artist', 'Nomalum') if music_result.get('success') else 'Nomalum'
                
                keyboard = [
                    [InlineKeyboardButton("🔄 Remix/Cover topish", callback_data=f"remix_{user_id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                with open(audio_path, 'rb') as audio_file:
                    await message.reply_audio(
                        audio=audio_file,
                        title=video_title,
                        performer=artist_name,
                        caption="🎵 Video katta bo'lgani uchun faqat audio yuborildi",
                        reply_markup=reply_markup,
                    )
                
                if music_result.get("success"):
                    user_music_data[user_id] = {
                        "title": music_result["title"],
                        "artist": music_result["artist"],
                        "audio_path": audio_path,
                    }
                    
                    # Musiqa ma'lumotlarini yuborish
                    text = recognizer.format_result(music_result)
                    await message.reply_text(text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
            else:
                error_msg = audio_result.get('error', 'Audio yuklab bolmadi')
                await status_msg.edit_text(f"❌ {error_msg}")
                return
        else:
            # Video yuborilgan bo'lsa, audio'ni fonda yuklab aniqlash
            audio_result = await downloader.download_audio(url, user_id)
            
            if audio_result.get("success"):
                await context.bot.send_chat_action(message.chat_id, ChatAction.TYPING)
                music_result = await recognizer.recognize_from_file(audio_result["filepath"])
                
                if music_result.get("success"):
                    user_music_data[user_id] = {
                        "title": music_result["title"],
                        "artist": music_result["artist"],
                        "audio_path": audio_result["filepath"],
                    }
        
        # Status xabarini o'chirish
        try:
            await status_msg.delete()
        except:
            pass
        
        # Video faylini o'chirish
        if video_path:
            downloader.cleanup_file(video_path)
        
    except Exception as e:
        logger.error(f"Link handle error: {e}")
        await status_msg.edit_text(MESSAGES["error"])


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Audio yuborilganda (Shazam)"""
    message = update.message
    user_id = message.from_user.id
    
    # Faylni olish
    if message.audio:
        file = message.audio
        file_name = file.file_name or f"{user_id}_audio.mp3"
    elif message.voice:
        file = message.voice
        file_name = f"{user_id}_voice.ogg"
    elif message.document and message.document.mime_type and 'audio' in message.document.mime_type:
        file = message.document
        file_name = file.file_name or f"{user_id}_document.mp3"
    else:
        return
    
    status_msg = await message.reply_text(MESSAGES["recognizing"])
    await context.bot.send_chat_action(message.chat_id, ChatAction.TYPING)
    
    try:
        # Faylni yuklab olish
        os.makedirs(DOWNLOAD_PATH, exist_ok=True)
        file_path = os.path.join(DOWNLOAD_PATH, file_name)
        
        telegram_file = await context.bot.get_file(file.file_id)
        await telegram_file.download_to_drive(file_path)
        
        # Musiqani aniqlash
        result = await recognizer.recognize_from_file(file_path)
        
        if result.get("success"):
            # Ma'lumotlarni saqlash
            user_music_data[user_id] = {
                "title": result["title"],
                "artist": result["artist"],
                "audio_path": file_path,
            }
            
            # Natijani yuborish
            text = recognizer.format_result(result)
            
            keyboard = [
                [InlineKeyboardButton("🔄 Remix/Cover topish", callback_data=f"remix_{user_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Agar cover art bo'lsa, rasm bilan yuborish
            if result.get("cover_art"):
                await message.reply_photo(
                    photo=result["cover_art"],
                    caption=text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup,
                )
            else:
                await message.reply_text(
                    text,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup,
                    disable_web_page_preview=True,
                )
        else:
            await message.reply_text(MESSAGES["no_music_found"])
        
        await status_msg.delete()
        
    except Exception as e:
        logger.error(f"Audio handle error: {e}")
        await status_msg.edit_text(MESSAGES["error"])


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback query handler"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    if data.startswith("audio_"):
        # Audio yuborish
        parts = data.split("_", 2)
        if len(parts) >= 2:
            await query.message.reply_text(MESSAGES["processing"])
            
            # Foydalanuvchi audio'sini yuborish
            if user_id in user_music_data and "audio_path" in user_music_data[user_id]:
                audio_path = user_music_data[user_id]["audio_path"]
                if os.path.exists(audio_path):
                    with open(audio_path, 'rb') as audio_file:
                        await query.message.reply_audio(
                            audio=audio_file,
                            title=user_music_data[user_id].get("title", "Audio"),
                            performer=user_music_data[user_id].get("artist", ""),
                        )
                else:
                    await query.message.reply_text("❌ Audio fayl topilmadi")
            else:
                await query.message.reply_text("❌ Audio ma'lumotlari topilmadi")
    
    elif data.startswith("remix_"):
        # Remix/Cover topish
        if user_id in user_music_data:
            music_data = user_music_data[user_id]
            title = music_data.get("title", "")
            artist = music_data.get("artist", "")
            
            if title and artist:
                await query.message.reply_text(MESSAGES["finding_remixes"])
                await context.bot.send_chat_action(query.message.chat_id, ChatAction.TYPING)
                
                results = await remix_finder.find_all_versions(title, artist)
                
                if results.get("success"):
                    all_results = results.get("remixes", []) + results.get("covers", [])
                    
                    if all_results:
                        # Natijalarni saqlash
                        user_search_data[f"remix_{user_id}"] = all_results
                        
                        # Inline keyboard yaratish
                        keyboard = []
                        for i, item in enumerate(all_results[:6]):
                            item_title = item.get("title", "")[:35]
                            duration = item.get("duration", "")
                            btn_text = f"🎧 {item_title}... ({duration})"
                            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"rmx_{i}_{user_id}")])
                        
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        
                        text_msg = f"""🔄 **Remix va Cover versiyalari**

🎵 **{title}** - {artist}

**{len(all_results)} ta natija topildi!**

Yuklab olish uchun birini tanlang 👇"""
                        
                        await query.message.reply_text(
                            text_msg,
                            parse_mode=ParseMode.MARKDOWN,
                            reply_markup=reply_markup
                        )
                    else:
                        await query.message.reply_text("😔 Remix/Cover topilmadi")
                else:
                    await query.message.reply_text("😔 Remix/Cover topilmadi")
            else:
                await query.message.reply_text("❌ Musiqa ma'lumotlari topilmadi")
        else:
            await query.message.reply_text("❌ Avval audio yuboring yoki link tashlang")
    
    elif data.startswith("rmx_"):
        # Remix yuklab olish
        try:
            parts = data.split("_")
            if len(parts) >= 3:
                index = int(parts[1])
                rmx_user_id = int(parts[2])
                
                key = f"remix_{rmx_user_id}"
                if key in user_search_data:
                    results = user_search_data[key]
                    if index < len(results):
                        item = results[index]
                        url = item.get("url", "")
                        
                        if url:
                            await query.message.reply_text("📥 Remix yuklanmoqda... ⚡")
                            await context.bot.send_chat_action(query.message.chat_id, ChatAction.UPLOAD_AUDIO)
                            
                            # Audio yuklab olish
                            audio_result = await downloader.download_audio(url, user_id)
                            
                            if audio_result.get("success"):
                                audio_path = audio_result["filepath"]
                                
                                with open(audio_path, 'rb') as audio_file:
                                    await query.message.reply_audio(
                                        audio=audio_file,
                                        title=item.get("title", "Remix"),
                                        performer=item.get("channel", ""),
                                        caption=f"🎧 **{item.get('title', 'Remix')}**\n👤 {item.get('channel', '')}"
                                    )
                                
                                downloader.cleanup_file(audio_path)
                            else:
                                await query.message.reply_text("❌ Yuklab bo'lmadi")
                        else:
                            await query.message.reply_text("❌ URL topilmadi")
                    else:
                        await query.message.reply_text("❌ Natija topilmadi")
                else:
                    await query.message.reply_text("❌ Qaytadan qidiring")
        except Exception as e:
            logger.error(f"Remix download error: {e}")
            await query.message.reply_text(MESSAGES["error"])
    
    elif data.startswith("dl_"):
        # Qidiruv natijasini yuklab olish
        try:
            parts = data.split("_")
            if len(parts) >= 3:
                index = int(parts[1])
                search_user_id = int(parts[2])
                
                if search_user_id in user_search_data:
                    results = user_search_data[search_user_id]
                    if index < len(results):
                        item = results[index]
                        url = item.get("url", "")
                        
                        if url:
                            await query.message.reply_text(MESSAGES["downloading"])
                            await context.bot.send_chat_action(query.message.chat_id, ChatAction.UPLOAD_AUDIO)
                            
                            # Audio yuklab olish
                            audio_result = await downloader.download_audio(url, user_id)
                            
                            if audio_result.get("success"):
                                audio_path = audio_result["filepath"]
                                
                                with open(audio_path, 'rb') as audio_file:
                                    await query.message.reply_audio(
                                        audio=audio_file,
                                        title=item.get("title", "Audio"),
                                        performer=item.get("channel", ""),
                                        caption=f"🎵 {item.get('title', 'Audio')}\n👤 {item.get('channel', '')}"
                                    )
                                
                                downloader.cleanup_file(audio_path)
                            else:
                                await query.message.reply_text("❌ Yuklab bo'lmadi")
                        else:
                            await query.message.reply_text("❌ URL topilmadi")
                    else:
                        await query.message.reply_text("❌ Natija topilmadi")
                else:
                    await query.message.reply_text("❌ Qaytadan qidiring")
        except Exception as e:
            logger.error(f"Download callback error: {e}")
            await query.message.reply_text(MESSAGES["error"])


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Matn xabarlari"""
    text = update.message.text.strip()
    user_id = update.message.from_user.id
    
    # URL bormi tekshirish
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    urls = re.findall(url_pattern, text)
    
    if urls:
        # URL topildi, link handler'ga yuborish
        await handle_link(update, context, urls[0])
    elif len(text) >= 2:
        # Qo'shiq nomi bilan qidirish
        status_msg = await update.message.reply_text(MESSAGES["searching"])
        await context.bot.send_chat_action(update.message.chat_id, ChatAction.TYPING)
        
        try:
            # YouTube'dan qidirish
            results = await searcher.search_by_name(text)
            
            if results.get("success") and results.get("results"):
                # Natijalarni saqlash
                user_search_data[user_id] = results.get("results", [])
                
                # Inline keyboard yaratish
                keyboard = []
                for i, item in enumerate(results.get("results", [])[:5]):
                    title = item.get("title", "")[:40]
                    duration = item.get("duration", "")
                    btn_text = f"🎵 {title}... ({duration})"
                    keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"dl_{i}_{user_id}")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                text_msg = f"""🔍 **Qidiruv: "{text}"**

🎵 **{len(results.get('results', []))} ta natija topildi!**

Yuklab olish uchun birini tanlang 👇"""
                
                await status_msg.edit_text(
                    text_msg,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=reply_markup
                )
            else:
                await status_msg.edit_text("😔 Hech narsa topilmadi. Boshqa nom bilan sinab ko'ring.")
        except Exception as e:
            logger.error(f"Search error: {e}")
            await status_msg.edit_text(MESSAGES["error"])
    else:
        await update.message.reply_text(
            "❓ Link yuboring yoki qo'shiq nomini yozing!",
            parse_mode=ParseMode.MARKDOWN,
        )


def format_duration(seconds) -> str:
    """Sekundlarni formatlash"""
    if not seconds:
        return "0:00"
    
    seconds = int(seconds)  # float bo'lsa int ga aylantirish
    minutes = seconds // 60
    secs = seconds % 60
    
    if minutes >= 60:
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours}:{mins:02d}:{secs:02d}"
    
    return f"{minutes}:{secs:02d}"


def main():
    """Botni ishga tushirish"""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN topilmadi! .env faylini tekshiring.")
        return
    
    # Downloads papkasini yaratish
    os.makedirs(DOWNLOAD_PATH, exist_ok=True)
    
    # Bot yaratish
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Handlerlarni qo'shish
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    
    # Audio handler
    application.add_handler(MessageHandler(
        filters.AUDIO | filters.VOICE | (filters.Document.AUDIO),
        handle_audio
    ))
    
    # Text/Link handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    # Callback handler
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    # Botni ishga tushirish
    logger.info("🤖 Bot ishga tushirildi!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
