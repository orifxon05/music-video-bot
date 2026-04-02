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

from config import BOT_TOKEN, MESSAGES, DOWNLOAD_PATH, WEBHOOK_URL, PORT, WEBHOOK_SECRET
from downloader import Downloader
from music_recognizer import MusicRecognizer
from remix_finder import RemixFinder
from music_searcher import MusicSearcher
from cache import cache
from database import db

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

downloader = Downloader()
recognizer = MusicRecognizer()
remix_finder = RemixFinder()
searcher = MusicSearcher()

# ==================== KANAL KESHI ====================
import time
CHANNELS_CACHE = {"data": None, "last_updated": 0, "ttl": 300}

async def get_cached_channels():
    current_time = time.time()
    if CHANNELS_CACHE["data"] is None or (current_time - CHANNELS_CACHE["last_updated"] > CHANNELS_CACHE["ttl"]):
        try:
            channels = db.get_channels()
            CHANNELS_CACHE["data"] = channels
            CHANNELS_CACHE["last_updated"] = current_time
            return channels
        except Exception as e:
            logger.error(f"Cache update error: {e}")
            return CHANNELS_CACHE["data"] or []
    return CHANNELS_CACHE["data"]

async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from config import ADMIN_ID
    user_id = update.effective_user.id
    if user_id == ADMIN_ID or user_id == 7693191223:
        return True

    channels = await get_cached_channels()
    if not channels:
        return True

    not_subscribed = []
    for channel in channels:
        try:
            chat_id = channel['channel_id']
            if not chat_id.startswith('-') and not chat_id.startswith('@'):
                chat_id = '@' + chat_id
            member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            if member.status in ['left', 'kicked']:
                not_subscribed.append(channel)
        except Exception as e:
            logger.error(f"Subscription check error for {channel.get('channel_id', '?')}: {e}")

    if not_subscribed:
        keyboard = []
        for ch in not_subscribed:
            ch_name = ch.get('name', "Kanalga o'tish")
            keyboard.append([InlineKeyboardButton(f"➕ {ch_name}", url=ch['url'])])
        keyboard.append([InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub")])

        msg_text = "❌ Botdan foydalanish uchun quyidagi kanallarga obuna bo'ling:"
        try:
            if update.callback_query:
                await update.callback_query.message.reply_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                await update.message.reply_text(msg_text, reply_markup=InlineKeyboardMarkup(keyboard))
        except Exception as e:
            logger.error(f"Subscription message error: {e}")
        return False

    return True

# ==================== HANDLERS ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db.add_user(user_id, update.effective_user.first_name, update.effective_user.username)
    if not await check_subscription(update, context):
        return
    await update.message.reply_text(MESSAGES["start"], parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_subscription(update, context):
        return
    await update.message.reply_text(MESSAGES["help"], parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from config import ADMIN_ID
    if update.effective_user.id not in (ADMIN_ID, 7693191223):
        return
    keyboard = [
        [InlineKeyboardButton("📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton("📢 Xabar yuborish", callback_data="admin_broadcast")],
        [InlineKeyboardButton("📢 Kanallar sozlamasi", callback_data="admin_channels")],
    ]
    await update.message.reply_text("👨‍💻 **Admin Panel**\n\nKerakli bo'limni tanlang:",
                                    reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from config import ADMIN_ID
    user_id = update.effective_user.id
    if user_id not in (ADMIN_ID, 7693191223):
        return

    stats = db.get_stats()
    files_count = 0
    if os.path.exists(DOWNLOAD_PATH):
        files_count = len([f for f in os.listdir(DOWNLOAD_PATH) if os.path.isfile(os.path.join(DOWNLOAD_PATH, f))])

    cache_stats = db.get_cache_stats()
    text = f"""📊 **Bot Statistikasi**

👥 Jami foydalanuvchilar: {stats['total_users']}
📥 Papkadagi fayllar: {files_count}
📥 Jami yuklashlar: {stats['total_downloads']}

⚡ **Kesh:**
🎵 Audio: {cache_stats.get('audio', 0)}
🎬 Video: {cache_stats.get('video', 0)}

🤖 Bot holati: Faol ✅"""

    target = update.message or (update.callback_query.message if update.callback_query else None)
    if target:
        await target.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str = None, status_msg=None):
    message = update.effective_message
    user_id = update.effective_user.id
    db.add_user(user_id, update.effective_user.first_name, update.effective_user.username)

    if not await check_subscription(update, context):
        return

    if url is None:
        url = message.text.strip()

    if not downloader.is_supported_url(url):
        await message.reply_text(MESSAGES["unsupported_link"])
        return

    db.increment_downloads()

    if not status_msg:
        status_msg = await message.reply_text(MESSAGES["downloading"])
    else:
        try:
            await status_msg.edit_text(MESSAGES["downloading"])
        except:
            pass

    try:
        await context.bot.send_chat_action(message.chat_id, "upload_video")
    except:
        pass

    # KESH TEKSHIRISH - Video
    cached_video_id = cache.get_video(url)
    if cached_video_id:
        try:
            await status_msg.edit_text("⚡ Keshdan topildi...")
            await message.reply_video(
                video=cached_video_id,
                caption=f"🎬 Video\n🔗 {url}\n\n⚡ Keshdan\n\n👉 @SavemuzikVideoBot",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🎵 Audio olish", callback_data=f"audio_{user_id}"),
                    InlineKeyboardButton("🔄 Remix/Cover", callback_data=f"remix_{user_id}"),
                ]])
            )
            db.save_user_session(user_id, {"url": url, "title": "Video", "artist": ""})
            await _delete_msg(status_msg)
            return
        except Exception as e:
            logger.warning(f"Keshdan video yuborishda xato: {e}")

    video_path = None
    audio_path = None

    try:
        video_result = await downloader.download_video(url, user_id)
        video_sent = False

        if video_result.get("success"):
            video_path = video_result["filepath"]
            file_size_mb = os.path.getsize(video_path) / (1024 * 1024)

            if file_size_mb <= 50:
                try:
                    await status_msg.edit_text("📤 Video yuborilmoqda...")
                    video_title = video_result.get('title', 'Video')
                    uploader = video_result.get('uploader', 'Nomalum')
                    duration = format_duration(video_result.get('duration', 0))
                    platform = video_result.get('platform', 'nomalum').title()

                    caption = (
                        f"🎬 **{video_title}**\n\n"
                        f"📱 Platform: {platform}\n"
                        f"👤 Muallif: {uploader}\n"
                        f"⏱ Davomiylik: {duration}\n\n"
                        f"👉 @SavemuzikVideoBot"
                    )
                    keyboard = [[
                        InlineKeyboardButton("🎵 Audio olish", callback_data=f"audio_{user_id}"),
                        InlineKeyboardButton("🔄 Remix/Cover", callback_data=f"remix_{user_id}"),
                    ]]

                    with open(video_path, 'rb') as vf:
                        sent_video = await message.reply_video(
                            video=vf, caption=caption,
                            reply_markup=InlineKeyboardMarkup(keyboard),
                        )
                    db.save_user_session(user_id, {"url": url, "title": video_title, "artist": uploader})
                    if sent_video.video:
                        cache.save_video(url, sent_video.video.file_id, video_title)
                    video_sent = True
                except Exception as ve:
                    logger.warning(f"Video yuborishda xato: {ve}")
            else:
                logger.info(f"Video hajmi katta ({file_size_mb:.1f}MB), faqat audio yuboriladi")

        # Audio yuborish (video yuborilmagan bo'lsa)
        if not video_sent:
            # Avval keshdan tekshirish
            cached_audio_id = cache.get_audio(url)
            if cached_audio_id:
                title = video_result.get('title', 'Audio') if video_result.get('success') else 'Audio'
                await message.reply_audio(
                    audio=cached_audio_id,
                    title=title,
                    caption="🎵 Keshdan audio\n\n👉 @SavemuzikVideoBot",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔄 Remix", callback_data=f"remix_{user_id}"),
                        InlineKeyboardButton("🎬 Video", callback_data=f"vid_{user_id}"),
                    ]])
                )
                db.save_user_session(user_id, {"url": url, "title": title})
                await _delete_msg(status_msg)
                return

            await status_msg.edit_text("🎵 Audio yuklanmoqda... ⚡")
            audio_result = await downloader.download_audio(url, user_id)

            if audio_result.get("success"):
                audio_path = audio_result["filepath"]
                video_title = video_result.get('title', 'Audio') if video_result.get('success') else 'Audio'

                db.save_user_session(user_id, {
                    "title": video_title, "artist": "",
                    "audio_path": audio_path, "url": url
                })

                keyboard = [[
                    InlineKeyboardButton("🎤 Shazam", callback_data=f"shazam_{user_id}"),
                    InlineKeyboardButton("🔄 Remix", callback_data=f"remix_{user_id}"),
                ], [
                    InlineKeyboardButton("🎬 Video yuklash", callback_data=f"vid_{user_id}"),
                ]]

                with open(audio_path, 'rb') as af:
                    sent_audio = await message.reply_audio(
                        audio=af, title=video_title,
                        performer=audio_result.get('uploader', 'Music Bot'),
                        caption="🎵 Audio tayyor!\n\n🎤 Shazam - qo'shiq nomini aniqlash\n🔄 Remix - versiyalarini topish\n\n👉 @SavemuzikVideoBot",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                    )
                if sent_audio.audio:
                    cache.save_audio(url, sent_audio.audio.file_id, video_title)
            else:
                err_msg = audio_result.get('error', "Audio yuklab bo'lmadi")
                await status_msg.edit_text(f"❌ {err_msg}")
                return
        else:
            # Video yuborildi, audio ham fonda saqlab qo'yish (keshda bo'lmasa)
            if not cache.get_audio(url):
                audio_result = await downloader.download_audio(url, user_id)
                if audio_result.get("success"):
                    audio_path = audio_result["filepath"]
                    db.save_user_session(user_id, {
                        "title": video_result.get('title', 'Audio'),
                        "artist": "", "audio_path": audio_path, "url": url
                    })

        await _delete_msg(status_msg)

    except Exception as e:
        logger.error(f"handle_link error: {e}")
        try:
            await status_msg.edit_text(MESSAGES["error"])
        except:
            pass
    finally:
        # Fayllarni tozalash
        if video_path:
            downloader.cleanup_file(video_path)
        if audio_path and not db.get_user_session(user_id):
            # Audio path session'da saqlangan bo'lsa, o'chirmaymiz
            pass


async def handle_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user_id = message.from_user.id
    db.add_user(user_id, update.effective_user.first_name, update.effective_user.username)
    if not await check_subscription(update, context):
        return

    try:
        file_id = None
        file_name = None

        if message.audio:
            file_id, file_name = message.audio.file_id, message.audio.file_name or f"{user_id}_audio.mp3"
        elif message.voice:
            file_id, file_name = message.voice.file_id, f"{user_id}_voice.ogg"
        elif message.video:
            if message.video.file_size > 20 * 1024 * 1024:
                await message.reply_text("❌ Video juda katta. 20MB dan kichik video yuboring.")
                return
            file_id, file_name = message.video.file_id, message.video.file_name or f"{user_id}_video.mp4"
        elif message.video_note:
            file_id, file_name = message.video_note.file_id, f"{user_id}_videonote.mp4"
        elif message.document:
            if message.document.mime_type and ('audio' in message.document.mime_type or 'video' in message.document.mime_type):
                if message.document.file_size > 20 * 1024 * 1024:
                    await message.reply_text("❌ Fayl juda katta. 20MB dan kichik bo'lishi kerak.")
                    return
                file_id = message.document.file_id
                file_name = message.document.file_name or f"{user_id}_doc"
            else:
                return
        else:
            return

        status_msg = await message.reply_text(MESSAGES["recognizing"])
        try:
            await context.bot.send_chat_action(message.chat_id, "upload_voice")
        except:
            pass

        os.makedirs(DOWNLOAD_PATH, exist_ok=True)
        file_path = os.path.join(DOWNLOAD_PATH, file_name)
        telegram_file = await context.bot.get_file(file_id)
        await telegram_file.download_to_drive(file_path)

        result = await recognizer.recognize_from_file(file_path)

        if result.get("success"):
            db.save_user_session(user_id, {
                "title": result["title"],
                "artist": result["artist"],
                "audio_path": file_path,
            })

            text = recognizer.format_result(result)
            keyboard = [[
                InlineKeyboardButton("📥 Qo'shiq yuklab olish", callback_data=f"dlsong_{user_id}"),
            ], [
                InlineKeyboardButton("🔄 Remix/Cover", callback_data=f"remix_{user_id}"),
                InlineKeyboardButton("🎬 Video", callback_data=f"vid_{user_id}"),
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            if result.get("cover_art"):
                await message.reply_photo(photo=result["cover_art"], caption=text,
                                          parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
            else:
                await message.reply_text(text, parse_mode=ParseMode.MARKDOWN,
                                         reply_markup=reply_markup, disable_web_page_preview=True)
        else:
            await message.reply_text(MESSAGES["no_music_found"])

        await _delete_msg(status_msg)

    except Exception as e:
        logger.error(f"handle_audio error: {e}")
        try:
            await status_msg.edit_text(MESSAGES["error"])
        except:
            pass


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    # ---- SHAZAM ----
    if data.startswith("shazam_"):
        session = db.get_user_session(user_id)
        if session and session.get("audio_path") and os.path.exists(session["audio_path"]):
            status_msg = await query.message.reply_text("🎤 Shazam aniqlamoqda...")
            music_result = await recognizer.recognize_from_file(session["audio_path"])
            if music_result.get("success"):
                db.save_user_session(user_id, {"title": music_result["title"], "artist": music_result["artist"]})
                await query.message.reply_text(recognizer.format_result(music_result),
                                               parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
            else:
                await query.message.reply_text("😔 Qo'shiq aniqlanmadi")
            await _delete_msg(status_msg)
        else:
            await query.message.reply_text("❌ Audio fayl topilmadi")

    # ---- AUDIO YUBORISH ----
    elif data.startswith("audio_"):
        session = db.get_user_session(user_id)
        status_msg = await query.message.reply_text(MESSAGES["processing"])
        if session and session.get("audio_path") and os.path.exists(session["audio_path"]):
            with open(session["audio_path"], 'rb') as af:
                await query.message.reply_audio(
                    audio=af, title=session.get("title", "Audio"),
                    performer=session.get("artist", ""),
                    caption="🎵 Audio\n\n👉 @SavemuzikVideoBot",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🎬 Video", callback_data=f"vid_{user_id}"),
                        InlineKeyboardButton("🔄 Remix", callback_data=f"remix_{user_id}"),
                    ]])
                )
            await _delete_msg(status_msg)
        else:
            await status_msg.edit_text("❌ Audio fayl topilmadi")

    # ---- REMIX ----
    elif data.startswith("remix_"):
        session = db.get_user_session(user_id)
        if session and session.get("title"):
            title = session.get("title", "")
            artist = session.get("artist", "")
            status_msg = await query.message.reply_text(MESSAGES["finding_remixes"])
            await context.bot.send_chat_action(query.message.chat_id, ChatAction.TYPING)

            results = await remix_finder.find_all_versions(title, artist)
            all_results = results.get("remixes", []) + results.get("covers", []) if results.get("success") else []

            if all_results:
                db.save_search_results(f"remix_{user_id}", all_results)
                keyboard = []
                for i, item in enumerate(all_results[:6]):
                    btn = f"🎧 {item.get('title', '')[:35]}... ({item.get('duration', '')})"
                    keyboard.append([InlineKeyboardButton(btn, callback_data=f"rmx_{i}_{user_id}")])

                text_msg = (f"🔄 **Remix va Cover versiyalari**\n\n"
                            f"🎵 **{title}** - {artist}\n\n"
                            f"**{len(all_results)} ta natija topildi!**\n\nYuklab olish uchun birini tanlang 👇")
                await status_msg.edit_text(text_msg, parse_mode=ParseMode.MARKDOWN,
                                           reply_markup=InlineKeyboardMarkup(keyboard))
            else:
                await status_msg.edit_text("😔 Remix/Cover topilmadi")
        else:
            await query.message.reply_text("❌ Musiqa ma'lumotlari topilmadi")

    # ---- REMIX YUKLAB OLISH ----
    elif data.startswith("rmx_"):
        try:
            parts = data.split("_")
            index, rmx_user_id = int(parts[1]), int(parts[2])
            results = db.get_search_results(f"remix_{rmx_user_id}")
            if results and index < len(results):
                item = results[index]
                url = item.get("url", "")
                if url:
                    cached_audio = cache.get_audio(url)
                    if cached_audio:
                        await query.message.reply_audio(
                            audio=cached_audio, title=item.get("title", "Remix"),
                            caption=f"🎧 **{item.get('title', 'Remix')}**\n⚡ Keshdan\n\n👉 @SavemuzikVideoBot",
                            reply_markup=InlineKeyboardMarkup([[
                                InlineKeyboardButton("🎬 Video", callback_data=f"vid_{user_id}"),
                                InlineKeyboardButton("🔄 Remix", callback_data=f"remix_{user_id}"),
                            ]])
                        )
                        db.save_user_session(user_id, {"url": url, "title": item.get("title", "Remix")})
                        return

                    status_msg = await query.message.reply_text("📥 Remix yuklanmoqda... ⚡")
                    audio_result = await downloader.download_audio(url, user_id)

                    if audio_result.get("success"):
                        audio_path = audio_result["filepath"]
                        try:
                            with open(audio_path, 'rb') as af:
                                sent = await query.message.reply_audio(
                                    audio=af, title=item.get("title", "Remix"),
                                    performer=item.get("channel", ""),
                                    caption=f"🎧 **{item.get('title', 'Remix')}**\n👤 {item.get('channel', '')}\n\n👉 @SavemuzikVideoBot",
                                    reply_markup=InlineKeyboardMarkup([[
                                        InlineKeyboardButton("🎬 Video", callback_data=f"vid_{user_id}"),
                                        InlineKeyboardButton("🔄 Remix", callback_data=f"remix_{user_id}"),
                                    ]])
                                )
                            db.save_user_session(user_id, {"url": url, "title": item.get("title", "Remix")})
                            if sent.audio:
                                cache.save_audio(url, sent.audio.file_id, item.get("title", ""))
                        finally:
                            downloader.cleanup_file(audio_path)
                        await _delete_msg(status_msg)
                    else:
                        err = audio_result.get('error', "Yuklab bo'lmadi"); await status_msg.edit_text(f"❌ {err}")
            else:
                await query.message.reply_text("❌ Natija topilmadi yoki kesh o'chgan")
        except Exception as e:
            logger.error(f"rmx error: {e}")
            await query.message.reply_text(MESSAGES["error"])

    # ---- VIDEO YUKLAB OLISH ----
    elif data.startswith("vid_"):
        status_msg = await query.message.reply_text("📥 Video yuklanmoqda... ⚡")
        session = db.get_user_session(user_id)
        url = session.get("url") if session else None

        if url:
            await handle_link(update, context, url, status_msg=status_msg)
        elif session:
            search_query = f"{session.get('title', '')} {session.get('artist', '')}".strip()
            if search_query:
                results = await searcher.search_by_name(search_query)
                if results.get("success") and results.get("results"):
                    await handle_link(update, context, results["results"][0]["url"], status_msg=status_msg)
                else:
                    await status_msg.edit_text("😔 Video topilmadi")
            else:
                await status_msg.edit_text("❌ Musiqa ma'lumotlari yetarli emas")
        else:
            await status_msg.edit_text("❌ Avval musiqa toping")

    # ---- OBUNA TEKSHIRISH ----
    elif data == "check_sub":
        if await check_subscription(update, context):
            try:
                await query.message.delete()
            except:
                pass
            await query.message.reply_text("✅ Rahmat! Endi botdan foydalanishingiz mumkin.")
            await start_command(update, context)
        else:
            await query.answer("❌ Hali ham hamma kanallarga a'zo emassiz!", show_alert=True)

    # ---- QOSHIQ YUKLAB OLISH (Shazam) ----
    elif data.startswith("dlsong_"):
        try:
            session = db.get_user_session(user_id)
            if not session or not session.get("title"):
                await query.message.reply_text("❌ Qo'shiq ma'lumotlari topilmadi")
                return

            title = session.get("title", "")
            artist = session.get("artist", "")
            search_query = f"{title} {artist}".strip()
            status_msg = await query.message.reply_text(f"📥 Qo'shiq yuklanmoqda...\n🔍 {search_query}")

            results = await searcher.search_by_name(search_query)
            if results.get("success") and results.get("results"):
                best_url = results["results"][0]["url"]

                cached_audio = cache.get_audio(best_url)
                if cached_audio:
                    await query.message.reply_audio(audio=cached_audio, title=title, performer=artist,
                                                    caption=f"🎵 {title}\n👤 {artist}\n⚡ Keshdan\n\n👉 @SavemuzikVideoBot")
                    await _delete_msg(status_msg)
                    return

                audio_result = await downloader.download_audio(best_url, user_id)
                if audio_result.get("success"):
                    audio_path = audio_result["filepath"]
                    try:
                        with open(audio_path, 'rb') as af:
                            sent = await query.message.reply_audio(audio=af, title=title, performer=artist,
                                                                   caption=f"🎵 {title}\n👤 {artist}\n\n👉 @SavemuzikVideoBot")
                        if sent.audio:
                            cache.save_audio(best_url, sent.audio.file_id, title)
                    finally:
                        downloader.cleanup_file(audio_path)
                    await _delete_msg(status_msg)
                else:
                    err_msg = audio_result.get('error', "Qo'shiq yuklab bo'lmadi"); await status_msg.edit_text(f"❌ {err_msg}")
            else:
                await status_msg.edit_text("😔 YouTube'dan topilmadi")
        except Exception as e:
            logger.error(f"dlsong error: {e}")
            await query.message.reply_text("❌ Kutilmagan xatolik")

    # ---- ADMIN ----
    elif data == "admin_stats":
        await stats_command(update, context)

    elif data == "admin_broadcast":
        context.user_data["admin_state"] = "broadcast"
        await query.message.reply_text("📣 **Xabar yuborish rejimi yoqildi.**\n\nMatnni yozing:",
                                       parse_mode=ParseMode.MARKDOWN)

    elif data == "admin_channels":
        channels = db.get_channels()
        text = "📢 **Majburiy a'zolik kanallari:**\n\n"
        keyboard = []
        if not channels:
            text += "Hozircha hech qanday kanal yo'q."
        else:
            for i, ch in enumerate(channels):
                text += f"{i+1}. {ch['name']} (ID: {ch['channel_id']})\n"
                keyboard.append([InlineKeyboardButton(f"❌ O'chirish: {ch['name']}", callback_data=f"del_ch_{i}")])
        keyboard.append([InlineKeyboardButton("➕ Kanal qo'shish", callback_data="add_ch")])
        keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="admin_menu")])
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

    elif data == "admin_menu":
        from config import ADMIN_ID
        if user_id in (ADMIN_ID, 7693191223):
            keyboard = [
                [InlineKeyboardButton("📊 Statistika", callback_data="admin_stats")],
                [InlineKeyboardButton("📢 Xabar yuborish", callback_data="admin_broadcast")],
                [InlineKeyboardButton("📢 Kanallar sozlamasi", callback_data="admin_channels")],
            ]
            await query.message.edit_text("👨‍💻 **Admin Panel**\n\nKerakli bo'limni tanlang:",
                                          reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

    elif data == "add_ch":
        context.user_data["admin_state"] = "add_channel"
        await query.message.reply_text(
            "📝 **Kanal qo'shish formatini yuboring:**\n\n`Nomi | ID | URL` \n\nMasalan:\n`Musiqa Kanali | -100123456789 | https://t.me/musiqa_kanali`",
            parse_mode=ParseMode.MARKDOWN)

    elif data.startswith("del_ch_"):
        index = int(data.split("_")[-1])
        db.remove_channel(index)
        await query.answer("✅ Kanal o'chirildi")
        # Keshni tozalash
        CHANNELS_CACHE["data"] = None
        # Menyu yangilash
        channels = db.get_channels()
        text = "📢 **Majburiy a'zolik kanallari:**\n\n"
        keyboard = []
        if not channels:
            text += "Hozircha hech qanday kanal yo'q."
        else:
            for i, ch in enumerate(channels):
                text += f"{i+1}. {ch['name']} (ID: {ch['channel_id']})\n"
                keyboard.append([InlineKeyboardButton(f"❌ O'chirish: {ch['name']}", callback_data=f"del_ch_{i}")])
        keyboard.append([InlineKeyboardButton("➕ Kanal qo'shish", callback_data="add_ch")])
        keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="admin_menu")])
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

    # ---- QIDIRUV NATIJASIDAN YUKLAB OLISH ----
    elif data.startswith("dl_"):
        try:
            parts = data.split("_")
            index, search_user_id = int(parts[1]), int(parts[2])
            results = db.get_search_results(search_user_id)

            if results and index < len(results):
                item = results[index]
                url = item.get("url", "")
                if url:
                    cached_file = cache.get_audio(url)
                    if cached_file:
                        await query.message.reply_audio(
                            audio=cached_file, title=item.get("title", "Audio"),
                            caption=f"🎵 {item.get('title', 'Audio')}\n⚡ Keshdan\n\n👉 @SavemuzikVideoBot",
                            reply_markup=InlineKeyboardMarkup([[
                                InlineKeyboardButton("🎬 Video", callback_data=f"vid_{user_id}"),
                                InlineKeyboardButton("🔄 Remix", callback_data=f"remix_{user_id}"),
                            ]])
                        )
                        db.save_user_session(user_id, {"url": url, "title": item.get("title", "Audio")})
                        return

                    status_msg = await query.message.reply_text(MESSAGES["downloading"])
                    audio_result = await downloader.download_audio(url, user_id)

                    if audio_result.get("success"):
                        audio_path = audio_result["filepath"]
                        try:
                            with open(audio_path, 'rb') as af:
                                sent = await query.message.reply_audio(
                                    audio=af, title=item.get("title", "Audio"),
                                    performer=item.get("channel", ""),
                                    caption=f"🎵 {item.get('title', 'Audio')}\n👤 {item.get('channel', '')}\n\n👉 @SavemuzikVideoBot",
                                    reply_markup=InlineKeyboardMarkup([[
                                        InlineKeyboardButton("🔄 Remix", callback_data=f"remix_{user_id}"),
                                        InlineKeyboardButton("🎬 Video", callback_data=f"vid_{user_id}"),
                                    ]])
                                )
                            db.save_user_session(user_id, {"url": url, "title": item.get("title", "Audio")})
                            if sent.audio:
                                cache.save_audio(url, sent.audio.file_id, item.get("title", ""))
                        finally:
                            downloader.cleanup_file(audio_path)
                        await _delete_msg(status_msg)
                    else:
                        err = audio_result.get('error', "Yuklab bo'lmadi"); await status_msg.edit_text(f"❌ {err}")
                else:
                    await query.message.reply_text("❌ URL topilmadi")
            else:
                await query.message.reply_text("❌ Natija topilmadi yoki kesh o'chgan. Qaytadan qidiring.")
        except Exception as e:
            logger.error(f"dl_ callback error: {e}")
            await query.message.reply_text(MESSAGES["error"])


async def broadcast_task(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    users = db.get_users()
    if not users:
        await update.message.reply_text("❌ Foydalanuvchilar topilmadi!")
        return

    msg = await update.message.reply_text(f"🚀 Xabar yuborish boshlandi: {len(users)} ta foydalanuvchiga...")
    count, errors = 0, 0

    for uid in users:
        try:
            try:
                await context.bot.send_message(chat_id=uid, text=text, parse_mode=ParseMode.HTML)
            except:
                await context.bot.send_message(chat_id=uid, text=text)
            count += 1
            if count % 20 == 0:
                await msg.edit_text(f"⏳ Jarayon: {count}/{len(users)} yuborildi...")
        except Exception as e:
            logger.error(f"Broadcast error for {uid}: {e}")
            errors += 1
        await asyncio.sleep(0.05)

    await update.message.reply_text(
        f"✅ **Xabar yuborish tugadi!**\n\n🟢 Muvaffaqiyatli: {count}\n🔴 Xato: {errors}",
        parse_mode=ParseMode.MARKDOWN
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.message.from_user.id
    db.add_user(user_id, update.effective_user.first_name, update.effective_user.username)

    from config import ADMIN_ID
    is_admin = (user_id in (ADMIN_ID, 7693191223))

    if is_admin:
        state = context.user_data.get("admin_state")
        if state == "broadcast":
            context.user_data["admin_state"] = None
            asyncio.create_task(broadcast_task(update, context, text))
            return
        elif state == "add_channel" or ("|" in text and len(text.split("|")) == 3):
            context.user_data["admin_state"] = None
            try:
                parts = [p.strip() for p in text.split("|")]
                name, ch_id, url = parts
                db.add_channel(ch_id, name, url)
                CHANNELS_CACHE["data"] = None  # keshni tozalash
                await update.message.reply_text(f"✅ **Kanal qo'shildi!**\n\nNom: {name}\nID: {ch_id}",
                                                parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                await update.message.reply_text(f"❌ Xatolik: {e}")
            return

    if not await check_subscription(update, context):
        return

    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    urls = re.findall(url_pattern, text)

    if urls:
        await handle_link(update, context, urls[0])
        return

    if len(text) >= 2:
        status_msg = await update.message.reply_text(MESSAGES["searching"])
        await context.bot.send_chat_action(update.message.chat_id, ChatAction.TYPING)

        try:
            results = await searcher.search_by_name(text)
            search_items = results.get("results")

            if results.get("success") and isinstance(search_items, list) and search_items:
                db.save_search_results(user_id, search_items)
                keyboard = []
                for i, item in enumerate(search_items[:10]):
                    if not isinstance(item, dict):
                        continue
                    item_title = str(item.get("title", "Audio"))[:35]
                    duration = item.get("duration")
                    dur_text = f" ({duration})" if duration and str(duration).lower() != "none" else ""
                    keyboard.append([InlineKeyboardButton(f"🎵 {item_title}{dur_text}", callback_data=f"dl_{i}_{user_id}")])

                if keyboard:
                    text_msg = (f"🔍 **Qidiruv: \"{text}\"**\n\n"
                                f"🎵 **{len(search_items)} ta natija topildi!**\n\nYuklab olish uchun birini tanlang 👇")
                    await status_msg.edit_text(text_msg, parse_mode=ParseMode.MARKDOWN,
                                              reply_markup=InlineKeyboardMarkup(keyboard))
                else:
                    await status_msg.edit_text("😔 Natija topilmadi.")
            else:
                await status_msg.edit_text("😔 Hech narsa topilmadi. Boshqa nom bilan sinab ko'ring.")
        except Exception as e:
            logger.error(f"Search error: {e}")
            await status_msg.edit_text(MESSAGES["error"])
    else:
        await update.message.reply_text("❓ Link yuboring yoki qo'shiq nomini yozing!")


# ==================== YORDAMCHI FUNKSIYALAR ====================

async def _delete_msg(msg):
    """Xabarni xavfsiz o'chirish"""
    try:
        await msg.delete()
    except:
        pass

def format_duration(seconds) -> str:
    if not seconds:
        return "0:00"
    seconds = int(seconds)
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


# ==================== MAIN ====================

def main():
    print("---------------------------------------------------")
    print(" >>> BOT ISHGA TUSHMOQDA...")
    print("---------------------------------------------------")

    if not BOT_TOKEN:
        logger.error("BOT_TOKEN topilmadi! .env faylini tekshiring.")
        return

    os.makedirs(DOWNLOAD_PATH, exist_ok=True)
    application = Application.builder().token(BOT_TOKEN).build()

    # Keshni tozalash (har 12 soatda)
    async def clear_cache_job(context: ContextTypes.DEFAULT_TYPE):
        cache.clear_old()
        logger.info("🧹 Eski keshlari tozalandi")

    application.job_queue.run_repeating(clear_cache_job, interval=12*3600, first=3600)

    # Handlerlar
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(MessageHandler(
        filters.AUDIO | filters.VOICE | filters.VIDEO | filters.VIDEO_NOTE | filters.Document.ALL,
        handle_audio
    ))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_handler(CallbackQueryHandler(handle_callback))

    if WEBHOOK_URL:
        webhook_url = WEBHOOK_URL
        if " = " in webhook_url:
            webhook_url = webhook_url.split(" = ")[-1].strip()
        if not webhook_url.endswith("/webhook"):
            webhook_url = f"{webhook_url.rstrip('/')}/webhook"

        logger.info(f"🌐 Webhook rejimi: {webhook_url} | Port: {PORT}")
        application.run_webhook(
            listen="0.0.0.0", port=PORT,
            url_path="/webhook", webhook_url=webhook_url,
            secret_token=WEBHOOK_SECRET,
            allowed_updates=Update.ALL_TYPES,
        )
    else:
        logger.info("🤖 Polling rejimi")
        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
