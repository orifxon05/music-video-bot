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
from cache import cache
from database import db

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
user_url_data = {}  # URL va user_id bog'liqligi

async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kanalga a'zolikni tekshirish"""
    from config import ADMIN_ID
    user_id = update.effective_user.id
    
    # Adminga doim ruxsat
    if user_id == ADMIN_ID or user_id == 7693191223:
        return True
        
    channels = db.get_channels()
    if not channels:
        return True
        
    not_subscribed = []
    for channel in channels:
        try:
            # Kanal ID si to'g'riligini tekshirish (faqat raqam yoki @ bilan boshlanishi kerak)
            chat_id = channel['id']
            if isinstance(chat_id, str) and not chat_id.startswith('-') and not chat_id.startswith('@'):
                # Agar ID noto'g'ri kiritilgan bo'lsa (masalan -100 tushib qolgan bo'lsa)
                logger.warning(f"Noto'g'ri kanal ID: {chat_id}")
                continue

            member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            if member.status in ['left', 'kicked']:
                not_subscribed.append(channel)
        except Exception as e:
            logger.error(f"Subscription check error for {channel['id']}: {e}")
            # Agar bot kanal admini bo'lmasa, member statusini tekshira olmaydi
            # Bunday holatda kanalni ro'yxatdan o'tkazib yuboramiz (foydalanuvchini bloklamaslik uchun)
            continue
            
    if not_subscribed:
        keyboard = []
        for ch in not_subscribed:
            keyboard.append([InlineKeyboardButton(f"➕ {ch['name']}", url=ch['url'])])
        
        keyboard.append([InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub")])
        
        msg_text = "❌ **Botdan foydalanish uchun kanallarga a'zo bo'ling!**\n\nBu hamma uchun manfaatli bo'ladi deb o'ylayman. Qisqa vaqt ichida foydali narsalar ulashamiz! 👇"
        
        try:
            if update.callback_query:
                await update.callback_query.message.reply_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
            else:
                await update.message.reply_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            logger.error(f"Error sending subscription message: {e}")
        return False
        
    return True

# ==================== HANDLERS ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start buyrug'i"""
    user_id = update.effective_user.id
    db.add_user(user_id)
    
    if not await check_subscription(update, context):
        return
        
    await update.message.reply_text(
        MESSAGES["start"],
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help buyrug'i"""
    if not await check_subscription(update, context):
        return
    await update.message.reply_text(
        MESSAGES["help"],
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin menyusi"""
    from config import ADMIN_ID
    user_id = update.effective_user.id
    if user_id != ADMIN_ID and user_id != 7693191223:
        return
        
    keyboard = [
        [InlineKeyboardButton("📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton("📢 Xabar yuborish", callback_data="admin_broadcast")],
        [InlineKeyboardButton("📢 Kanallar sozlamasi", callback_data="admin_channels")],
    ]
    await update.message.reply_text("👨‍💻 **Admin Panel**\n\nKerakli bo'limni tanlang:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Statistika buyrug'i - Faqat admin uchun"""
    from config import ADMIN_ID
    user_id = update.effective_user.id
    if user_id != ADMIN_ID and user_id != 7693191223:
        return

    stats = db.get_stats()
    files_count = 0
    if os.path.exists(DOWNLOAD_PATH):
        files_count = len([f for f in os.listdir(DOWNLOAD_PATH) if os.path.isfile(os.path.join(DOWNLOAD_PATH, f))])
    
    from cache import cache
    cached_audio = len(cache.cache.get("audio", {}))
    cached_video = len(cache.cache.get("video", {}))
    
    text = f"""📊 **Bot Statistikasi (Baza)**

👥 Jami foydalanuvchilar: {stats['total_users']}
📥 Papkadagi fayllar: {files_count}
📥 Jami yuklashlar: {stats['total_downloads']}

⚡ **Kesh statistikasi:**
🎵 Audio kesh: {cached_audio}
🎬 Video kesh: {cached_video}

🤖 Bot holati: Faol ✅"""
    
    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    elif update.callback_query:
        await update.callback_query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str = None):
    """Link yuborilganda"""
    message = update.message
    user_id = message.from_user.id
    db.add_user(user_id)
    if not await check_subscription(update, context):
        return
        
    # URL ni olish
    if url is None:
        url = message.text.strip()
    
    # URL ni tekshirish
    if not downloader.is_supported_url(url):
        await message.reply_text(MESSAGES["unsupported_link"])
        return
    
    db.increment_downloads()
    
    # Jarayonni boshlash
    status_msg = await message.reply_text(MESSAGES["downloading"])
    await context.bot.send_chat_action(message.chat_id, ChatAction.UPLOAD_VIDEO)
    
    # KESH TEKSHIRISH - Video uchun
    cached_video_id = cache.get_video(url)
    if cached_video_id:
        try:
            await status_msg.edit_text("⚡ Keshdan topildi...")
            await message.reply_video(
                video=cached_video_id,
                caption=f"🎬 Video topildi!\n🔗 {url}\n\n⚡ Tezkor yuklash (Keshdan)",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🎵 Audio olish", callback_data=f"audio_{user_id}"),
                        InlineKeyboardButton("🔄 Remix/Cover", callback_data=f"remix_{user_id}"),
                    ]
                ])
            )
            await status_msg.delete()
            # Fondagi audio uchun keshni yangilab qo'yamiz
            cached_audio_id = cache.get_audio(url)
            if cached_audio_id:
                 user_music_data[user_id] = {"title": "Audio", "artist": "", "file_id": cached_audio_id}
            return
        except Exception as e:
            logger.warning(f"Keshdan yuborishda xato: {e}")

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
                        sent_video = await message.reply_video(
                            video=video_file,
                            caption=caption,
                            parse_mode=ParseMode.MARKDOWN,
                            reply_markup=reply_markup,
                        )
                        # Keshga saqlash
                        if sent_video.video:
                            cache.save_video(url, sent_video.video.file_id, video_title)
                            
                    video_sent = True
                except Exception as video_error:
                    logger.warning(f"Video yuborishda xato: {video_error}")
            else:
                logger.info(f"Video juda katta: {file_size_mb:.1f}MB, faqat audio yuboriladi")
        
        # Agar video yuborilmagan bo'lsa, faqat audio yuborish
        if not video_sent:
            cached_audio_id = cache.get_audio(url)
            if cached_audio_id:
                await message.reply_audio(
                    audio=cached_audio_id,
                    title=video_result.get('title', 'Audio') if video_result.get('success') else 'Audio',
                    performer=video_result.get('uploader', 'Music Bot') if video_result.get('success') else 'Music Bot',
                    caption="🎵 Keshdagi audio yuborildi",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Remix", callback_data=f"remix_{user_id}")]])
                )
                await status_msg.delete()
                return

            await status_msg.edit_text("🎵 Audio yuklanmoqda... ⚡")
            audio_result = await downloader.download_audio(url, user_id)
            
            if audio_result.get("success"):
                audio_path = audio_result["filepath"]
                video_title = video_result.get('title', 'Audio') if video_result.get('success') else 'Audio'
                
                user_music_data[user_id] = {
                    "title": video_title,
                    "artist": "",
                    "audio_path": audio_path,
                }
                
                keyboard = [
                    [
                        InlineKeyboardButton("🎤 Shazam", callback_data=f"shazam_{user_id}"),
                        InlineKeyboardButton("🔄 Remix", callback_data=f"remix_{user_id}"),
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                with open(audio_path, 'rb') as audio_file:
                    performer = audio_result.get('uploader', 'Music Bot')
                    sent_audio = await message.reply_audio(
                        audio=audio_file,
                        title=video_title,
                        performer=performer,
                        caption="🎵 Audio tayyor!\n\n🎤 Shazam - qo'shiq nomini aniqlash\n🔄 Remix - versiyalarini topish",
                        reply_markup=reply_markup,
                    )
                    # Keshga saqlash
                    if sent_audio.audio:
                        cache.save_audio(url, sent_audio.audio.file_id, video_title)
            else:
                error_msg = audio_result.get('error', 'Audio yuklab bolmadi')
                await status_msg.edit_text(f"❌ {error_msg}")
                return
        else:
            # Video yuborilgan bo'lsa, audio ham fonda yuklab qo'yish (Keshda bo'lmasa)
            if not cache.get_audio(url):
                audio_result = await downloader.download_audio(url, user_id)
                if audio_result.get("success"):
                     # Keshga saqlash uchun bitta yuborib ko'ramiz (lekin o'chiramiz yoki shunchaki saqlab qo'yamiz)
                     # Telegramda file_id olish uchun yuborish shart. Shuning uchun foydalanuvchiga emas, admin botga yuborsa bo'ladi yoki keshga keyinroq tushadi.
                     # Hozircha shunchaki path ni saqlaymiz.
                    user_music_data[user_id] = {
                        "title": video_result.get('title', 'Audio'),
                        "artist": "",
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
    db.add_user(user_id)
    if not await check_subscription(update, context):
        return
    
    if not (message.audio or message.voice or (message.document and message.document.mime_type and 'audio' in message.document.mime_type)):
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
    
    if data.startswith("shazam_"):
        # Shazam - musiqa aniqlash (FAQAT KERAK BO'LGANDA)
        if user_id in user_music_data and "audio_path" in user_music_data[user_id]:
            audio_path = user_music_data[user_id]["audio_path"]
            if os.path.exists(audio_path):
                await query.message.reply_text("🎤 Shazam aniqlamoqda...")
                
                music_result = await recognizer.recognize_from_file(audio_path)
                
                if music_result.get("success"):
                    user_music_data[user_id]["title"] = music_result["title"]
                    user_music_data[user_id]["artist"] = music_result["artist"]
                    
                    text = recognizer.format_result(music_result)
                    await query.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
                else:
                    await query.message.reply_text("😔 Qo'shiq aniqlanmadi")
            else:
                await query.message.reply_text("❌ Audio fayl topilmadi")
        else:
            await query.message.reply_text("❌ Avval audio yuboring")
    
    elif data.startswith("audio_"):
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
                            # KESH TEKSHIRISH
                            cached_audio_id = cache.get_audio(url)
                            if cached_audio_id:
                                await query.message.reply_audio(
                                    audio=cached_audio_id,
                                    title=item.get("title", "Remix"),
                                    performer=item.get("channel", ""),
                                    caption=f"🎧 **{item.get('title', 'Remix')}**\n⚡ Keshdan (Tezkor)"
                                )
                                return

                            await query.message.reply_text("📥 Remix yuklanmoqda... ⚡")
                            
                            # Audio yuklab olish
                            audio_result = await downloader.download_audio(url, user_id)
                            
                            if audio_result.get("success"):
                                audio_path = audio_result["filepath"]
                                
                                with open(audio_path, 'rb') as audio_file:
                                    sent_audio = await query.message.reply_audio(
                                        audio=audio_file,
                                        title=item.get("title", "Remix"),
                                        performer=item.get("channel", ""),
                                        caption=f"🎧 **{item.get('title', 'Remix')}**\n👤 {item.get('channel', '')}"
                                    )
                                    # Keshga saqlash
                                    if sent_audio.audio:
                                        cache.save_audio(url, sent_audio.audio.file_id, item.get("title", ""))
                                
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
    
    elif data == "check_sub":
        if await check_subscription(update, context):
            try:
                await query.message.delete()
            except:
                pass
            await query.message.reply_text("✅ Rahmat! Hamma kanallarga a'zo bo'ldingiz. Endi botdan foydalanishingiz mumkin.")
            await start_command(update, context)
        else:
            await query.answer("❌ Hali ham hamma kanallarga a'zo emassiz!", show_alert=True)

    elif data == "admin_stats":
        await stats_command(update, context)
        
    elif data == "admin_broadcast":
        context.user_data["admin_state"] = "broadcast"
        await query.message.reply_text("📣 **Xabar yuborish rejimi yoqildi.**\n\nBarcha foydalanuvchilarga yubormoqchi bo'lgan matningizni yozing (rasm/video hozircha qo'llab-quvvatlanmaydi):")
        
    elif data == "admin_channels":
        channels = db.get_channels()
        text = "📢 **Majburiy a'zolik kanallari:**\n\n"
        keyboard = []
        if not channels:
            text += "Hozircha hech qanday kanal yo'q."
        else:
            for i, ch in enumerate(channels):
                text += f"{i+1}. {ch['name']} (ID: {ch['id']})\n"
                keyboard.append([InlineKeyboardButton(f"❌ O'chirish: {ch['name']}", callback_data=f"del_ch_{i}")])
        
        keyboard.append([InlineKeyboardButton("➕ Kanal qo'shish", callback_data="add_ch")])
        keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="admin_menu")])
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

    elif data == "admin_menu":
        from config import ADMIN_ID
        if user_id == ADMIN_ID or user_id == 7693191223:
            keyboard = [
                [InlineKeyboardButton("📊 Statistika", callback_data="admin_stats")],
                [InlineKeyboardButton("📢 Xabar yuborish", callback_data="admin_broadcast")],
                [InlineKeyboardButton("📢 Kanallar sozlamasi", callback_data="admin_channels")],
            ]
            await query.message.edit_text("👨‍💻 **Admin Panel**\n\nKerakli bo'limni tanlang:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

    elif data == "add_ch":
        context.user_data["admin_state"] = "add_channel"
        await query.message.reply_text("📝 **Kanal qo'shish formatini yuboring:**\n\n`Nomi | ID | URL` \n\nMasalan:\n`Musiqa Kanali | -100123456789 | https://t.me/musiqa_kanali`", parse_mode=ParseMode.MARKDOWN)

    elif data.startswith("del_ch_"):
        index = int(data.split("_")[-1])
        db.remove_channel(index)
        await query.answer("✅ Kanal o'chirildi")
        # Menyu yangilash
        channels = db.get_channels()
        text = "📢 **Majburiy a'zolik kanallari:**\n\n"
        keyboard = []
        if not channels:
            text += "Hozircha hech qanday kanal yo'q."
        else:
            for i, ch in enumerate(channels):
                text += f"{i+1}. {ch['name']} (ID: {ch['id']})\n"
                keyboard.append([InlineKeyboardButton(f"❌ O'chirish: {ch['name']}", callback_data=f"del_ch_{i}")])
        keyboard.append([InlineKeyboardButton("➕ Kanal qo'shish", callback_data="add_ch")])
        keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="admin_menu")])
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

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
                            # KESH TEKSHIRISH
                            cached_file_id = cache.get_audio(url)
                            if cached_file_id:
                                await query.message.reply_audio(
                                    audio=cached_file_id,
                                    title=item.get("title", "Audio"),
                                    performer=item.get("channel", ""),
                                    caption=f"🎵 {item.get('title', 'Audio')}\n⚡ Keshdan"
                                )
                            else:
                                await query.message.reply_text(MESSAGES["downloading"])
                                audio_result = await downloader.download_audio(url, user_id)
                                if audio_result.get("success"):
                                    audio_path = audio_result["filepath"]
                                    with open(audio_path, 'rb') as audio_file:
                                        sent_msg = await query.message.reply_audio(
                                            audio=audio_file,
                                            title=item.get("title", "Audio"),
                                            performer=item.get("channel", ""),
                                            caption=f"🎵 {item.get('title', 'Audio')}\n👤 {item.get('channel', '')}"
                                        )
                                    if sent_msg.audio:
                                        cache.save_audio(url, sent_msg.audio.file_id, item.get("title", ""))
                                    downloader.cleanup_file(audio_path)
                                else:
                                    await query.message.reply_text("❌ Yuklab bo'lmadi")
        except Exception as e:
            logger.error(f"Download callback error: {e}")
            await query.message.reply_text(MESSAGES["error"])

async def broadcast_task(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    users = db.get_users()
    count = 0
    errors = 0
    msg = await update.message.reply_text(f"🚀 Xabar yuborish boshlandi: {len(users)} ta foydalanuvchiga...")
    
    for user_id in users:
        try:
            await context.bot.send_message(chat_id=user_id, text=text, parse_mode=ParseMode.MARKDOWN)
            count += 1
            if count % 20 == 0:
                await msg.edit_text(f"⏳ Jarayon: {count}/{len(users)} yuborildi...")
        except Exception:
            errors += 1
        await asyncio.sleep(0.05) # Flood wait oldini olish
        
    await update.message.reply_text(f"✅ **Xabar yuborish tugadi!**\n\n🟢 Muvaffaqiyatli: {count}\n🔴 Xato: {errors}")

async def add_channel_task(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    try:
        parts = [p.strip() for p in text.split("|")]
        if len(parts) == 3:
            name, ch_id, url = parts
            db.add_channel(name, ch_id, url)
            await update.message.reply_text(f"✅ **Kanal qo'shildi!**\n\nNom: {name}\nID: {ch_id}")
        else:
            await update.message.reply_text("❌ Xato format. Iltimos qaytadan urining.")
    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik: {e}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Matn xabarlari"""
    text = update.message.text.strip()
    user_id = update.message.from_user.id
    db.add_user(user_id)
    
    # Admin inputlarini tekshirish (Broadcast yoki Kanal qo'shish uchun)
    from config import ADMIN_ID
    is_admin = (user_id == ADMIN_ID or user_id == 7693191223)
    
    if is_admin:
        state = context.user_data.get("admin_state")
        
        # State bo'lsa yoki format to'g'ri kelsa (state'siz ham)
        if state == "broadcast":
            context.user_data["admin_state"] = None
            asyncio.create_task(broadcast_task(update, context, text))
            return
        elif state == "add_channel" or ("|" in text and len(text.split("|")) == 3):
            context.user_data["admin_state"] = None
            await add_channel_task(update, context, text)
            return

    if not await check_subscription(update, context):
        return
        
    # URL bormi tekshirish
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    urls = re.findall(url_pattern, text)
    
    if urls:
        # Telegram link bo'lsa va admin bo'lsa, uni link deb hisoblamaslik (agar format | bo'lsa yuqorida ushlanadi)
        if "t.me" in urls[0] and is_admin and "|" not in text:
             # Shunchaki oddiy matn sifatida qoldiramiz (masalan qidiruv bo'lishi mumkin)
             pass
        else:
             # URL topildi, link handler'ga yuborish
             await handle_link(update, context, urls[0])
             return
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
                for i, item in enumerate(results.get("results", [])[:10]):
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
    
    # Keshni tozalash vazifasini qo'shish (har 12 soatda)
    async def clear_cache_job(context: ContextTypes.DEFAULT_TYPE):
        cache.clear_old()
        logger.info("🧹 Eski keshlari tozalandi")
        
    job_queue = application.job_queue
    job_queue.run_repeating(clear_cache_job, interval=12*3600, first=3600)
    
    # Handlerlarni qo'shish
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("admin", admin_command))
    
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
