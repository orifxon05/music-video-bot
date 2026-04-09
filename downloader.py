import logging
import asyncio
import os
import httpx
import yt_dlp
import re
from config import DOWNLOAD_PATH, PROXY_URL, MAX_FILE_SIZE_MB
import pathlib

logger = logging.getLogger(__name__)

# ==================== PO_TOKEN SOZLAMASI ====================
# YouTube bot blokini chetlab o'tish uchun po_token kerak.
# Quyidagi saytdan oling: https://www.youtube.com/watch?v=dQw4w9WgXcQ
# F12 -> Console -> ytcfg.get("VISITOR_DATA") va po_token ni oling
# Yoki Railway Environment Variables ga PO_TOKEN va VISITOR_DATA qo'shing
PO_TOKEN = os.getenv("PO_TOKEN", "")
VISITOR_DATA = os.getenv("VISITOR_DATA", "")


class Downloader:
    def __init__(self):
        self.download_path = DOWNLOAD_PATH
        os.makedirs(self.download_path, exist_ok=True)

    def is_supported_url(self, url: str) -> bool:
        supported_domains = [
            'youtube.com', 'youtu.be', 'instagram.com', 'tiktok.com',
            'facebook.com', 'twitter.com', 'x.com', 'soundcloud.com'
        ]
        return any(domain in url.lower() for domain in supported_domains)

    def _find_cookie_file(self, url: str) -> str | None:
        if any(d in url.lower() for d in ['youtube.com', 'youtu.be']):
            candidates = ['youtube_cookies.txt', 'cookies.txt', 'www.youtube.com_cookies.txt']
        elif 'instagram.com' in url.lower():
            candidates = ['www.instagram.com_cookies.txt', 'instagram_cookies.txt', 'cookies.txt']
        else:
            candidates = ['cookies.txt']
        for cookie_file in candidates:
            if os.path.exists(cookie_file):
                return str(pathlib.Path(cookie_file).resolve())
        return None

    def _is_youtube_url(self, url: str) -> bool:
        return any(d in url.lower() for d in ['youtube.com', 'youtu.be'])

    def _extract_youtube_id(self, url: str) -> str | None:
        patterns = [
            r'(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([a-zA-Z0-9_-]{11})',
            r'^([a-zA-Z0-9_-]{11})$'
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    # ==================== 1. INVIDIOUS ====================
    async def download_with_invidious(self, url: str, user_id: int, is_video: bool = True) -> dict:
        video_id = self._extract_youtube_id(url)
        if not video_id:
            return {"success": False, "error": "YouTube video ID topilmadi"}

        INVIDIOUS_INSTANCES = [
            "https://inv.nadeko.net",
            "https://inv.tux.pizza",
            "https://invidious.privacydev.net",
            "https://invidious.fdn.fr",
            "https://invidious.io.lol",
            "https://y.com.sb",
            "https://invidious.lunar.icu",
            "https://invidious.tiekoetter.com",
            "https://invidious.projectsegfau.lt",
            "https://invidious.nerdvpn.de",
            "https://iv.datura.network",
            "https://yt.artemislena.eu",
        ]

        async with httpx.AsyncClient(timeout=15.0, verify=False, follow_redirects=True) as client:
            for instance in INVIDIOUS_INSTANCES:
                try:
                    resp = await client.get(
                        f"{instance}/api/v1/videos/{video_id}",
                        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                    )
                    if resp.status_code != 200:
                        logger.warning(f"⚠️ Invidious {instance}: {resp.status_code}")
                        continue

                    text = resp.text.strip()
                    if not text or not text.startswith('{'):
                        logger.warning(f"⚠️ Invidious {instance}: bo'sh javob")
                        continue

                    data = resp.json()
                    if data.get("error"):
                        logger.warning(f"⚠️ Invidious {instance}: {data.get('error')}")
                        continue

                    title = data.get("title", "video")
                    dl_url = None

                    if is_video:
                        for fmt in data.get("formatStreams", []):
                            if fmt.get("type", "").startswith("video/mp4"):
                                if any(q in fmt.get("qualityLabel", "") for q in ["720p", "480p", "360p"]):
                                    dl_url = fmt.get("url")
                                    break
                        if not dl_url:
                            for fmt in data.get("formatStreams", []):
                                if fmt.get("type", "").startswith("video/mp4"):
                                    dl_url = fmt.get("url")
                                    break
                    else:
                        best_bitrate = 0
                        for fmt in data.get("adaptiveFormats", []):
                            if fmt.get("type", "").startswith("audio/"):
                                br = fmt.get("bitrate", 0)
                                if br > best_bitrate:
                                    best_bitrate = br
                                    dl_url = fmt.get("url")

                    if not dl_url:
                        logger.warning(f"⚠️ Invidious {instance}: URL topilmadi")
                        continue

                    filename = f"{user_id}_{os.urandom(4).hex()}"
                    ext = "mp4" if is_video else "mp3"
                    filepath = os.path.join(self.download_path, f"{filename}.{ext}")

                    async with client.stream("GET", dl_url, timeout=120.0) as response:
                        if response.status_code != 200:
                            continue
                        with open(filepath, "wb") as f:
                            async for chunk in response.aiter_bytes(chunk_size=65536):
                                f.write(chunk)

                    size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
                    if size > 10_000:
                        logger.info(f"✅ Invidious success: {instance}")
                        return {
                            "success": True, "filepath": filepath, "title": title,
                            "uploader": data.get("author", ""), "duration": data.get("lengthSeconds", 0),
                            "platform": "youtube"
                        }
                    if os.path.exists(filepath):
                        os.remove(filepath)

                except Exception as e:
                    logger.warning(f"❌ Invidious {instance}: {str(e)[:80]}")

        return {"success": False, "error": "Invidious ishlamadi"}

    # ==================== 2. PIPED ====================
    async def download_with_piped(self, url: str, user_id: int, is_video: bool = True) -> dict:
        video_id = self._extract_youtube_id(url)
        if not video_id:
            return {"success": False, "error": "YouTube video ID topilmadi"}

        PIPED_INSTANCES = [
            "https://piped-api.garudalinux.org",
            "https://pipedapi.tokhmi.xyz",
            "https://pipedapi.moomoo.me",
            "https://pa.il.senny.xyz",
            "https://api.piped.projectsegfau.lt",
            "https://pipedapi.kavin.rocks",
        ]

        async with httpx.AsyncClient(timeout=15.0, verify=False, follow_redirects=True) as client:
            for instance in PIPED_INSTANCES:
                try:
                    resp = await client.get(
                        f"{instance}/streams/{video_id}",
                        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                    )
                    if resp.status_code != 200:
                        logger.warning(f"⚠️ Piped {instance}: {resp.status_code}")
                        continue

                    text = resp.text.strip()
                    if not text or not text.startswith('{'):
                        logger.warning(f"⚠️ Piped {instance}: bo'sh javob")
                        continue

                    data = resp.json()
                    if data.get("error"):
                        continue

                    title = data.get("title", "video")
                    dl_url = None

                    if is_video:
                        for stream in data.get("videoStreams", []):
                            if not stream.get("videoOnly", True):
                                if "720p" in stream.get("quality", "") or "480p" in stream.get("quality", ""):
                                    dl_url = stream.get("url")
                                    break
                        if not dl_url:
                            for stream in data.get("videoStreams", []):
                                if not stream.get("videoOnly", True):
                                    dl_url = stream.get("url")
                                    break
                    else:
                        best_br = 0
                        for stream in data.get("audioStreams", []):
                            br = stream.get("bitrate", 0)
                            if br > best_br:
                                best_br = br
                                dl_url = stream.get("url")

                    if not dl_url:
                        continue

                    filename = f"{user_id}_{os.urandom(4).hex()}"
                    ext = "mp4" if is_video else "mp3"
                    filepath = os.path.join(self.download_path, f"{filename}.{ext}")

                    async with client.stream("GET", dl_url, timeout=120.0) as response:
                        if response.status_code != 200:
                            continue
                        with open(filepath, "wb") as f:
                            async for chunk in response.aiter_bytes(chunk_size=65536):
                                f.write(chunk)

                    size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
                    if size > 10_000:
                        logger.info(f"✅ Piped success: {instance}")
                        return {
                            "success": True, "filepath": filepath, "title": title,
                            "uploader": data.get("uploader", ""), "duration": data.get("duration", 0),
                            "platform": "youtube"
                        }
                    if os.path.exists(filepath):
                        os.remove(filepath)

                except Exception as e:
                    logger.warning(f"❌ Piped {instance}: {str(e)[:80]}")

        return {"success": False, "error": "Piped ishlamadi"}

    # ==================== 3. YT-DLP (PO_TOKEN BILAN) ====================
    async def download_with_ytdlp(self, url: str, user_id: int, is_video: bool = True) -> dict:
        """yt-dlp — po_token bilan YouTube bot blokini chetlab o'tish"""

        player_clients_list = [
            ['android'],
            ['ios'],
            ['web'],
            ['tv'],
        ]

        for player_clients in player_clients_list:
            result = await self._ytdlp_attempt(url, user_id, is_video, player_clients)
            if result.get("success"):
                return result
            err = result.get("error", "")
            if "Sign in" not in err and "bot" not in err.lower() and "confirm" not in err.lower():
                return result

        return {"success": False, "error": "yt-dlp: YouTube bu serverdan yuklab bo'lmaydi"}

    async def _ytdlp_attempt(self, url: str, user_id: int, is_video: bool, player_clients: list) -> dict:
        try:
            filename = f"{user_id}_{os.urandom(4).hex()}"
            filepath_template = os.path.join(self.download_path, f"{filename}.%(ext)s")

            extractor_args = {
                'youtube': {
                    'player_client': player_clients,
                }
            }

            # PO_TOKEN mavjud bo'lsa qo'shish (bot blokini chetlab o'tadi)
            if PO_TOKEN:
                extractor_args['youtube']['po_token'] = [f'web+{PO_TOKEN}']
                if VISITOR_DATA:
                    extractor_args['youtube']['visitor_data'] = [VISITOR_DATA]
                logger.info(f"🔑 po_token ishlatilmoqda")

            ydl_opts = {
                'outtmpl': filepath_template,
                'quiet': True,
                'no_warnings': True,
                'nocheckcertificate': True,
                'geo_bypass': True,
                'socket_timeout': 30,
                'retries': 3,
                'extractor_args': extractor_args,
            }

            if not is_video:
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
            # format ni umuman belgilamaymiz — yt-dlp o'zi eng yaxshisini tanlaydi

            cookie_file = self._find_cookie_file(url)
            if cookie_file:
                ydl_opts['cookiefile'] = cookie_file

            if PROXY_URL:
                ydl_opts['proxy'] = PROXY_URL

            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(
                None, lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=True)
            )

            title = info.get('title', 'video') if info else 'video'
            ext = "mp3" if not is_video else "mp4"
            filepath = os.path.join(self.download_path, f"{filename}.{ext}")

            if not os.path.exists(filepath):
                for f in os.listdir(self.download_path):
                    if f.startswith(filename):
                        filepath = os.path.join(self.download_path, f)
                        break

            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                logger.info(f"✅ yt-dlp success (clients={player_clients})")
                return {
                    "success": True, "filepath": filepath, "title": title,
                    "uploader": info.get('uploader', '') if info else '',
                    "duration": info.get('duration', 0) if info else 0,
                    "platform": info.get('extractor', 'unknown') if info else 'unknown'
                }

            return {"success": False, "error": "Fayl yaratilmadi"}

        except Exception as e:
            logger.error(f"yt-dlp ({player_clients}): {str(e)[:120]}")
            return {"success": False, "error": str(e)[:100]}

    # ==================== 4. BOSHQA PLATFORMALAR ====================
    async def download_non_youtube(self, url: str, user_id: int, is_video: bool = True) -> dict:
        try:
            filename = f"{user_id}_{os.urandom(4).hex()}"
            ydl_opts = {
                'outtmpl': os.path.join(self.download_path, f"{filename}.%(ext)s"),
                'quiet': True,
                'no_warnings': True,
                'nocheckcertificate': True,
                'socket_timeout': 30,
                'retries': 3,
                'format': 'best[filesize<50M]/best' if is_video else 'bestaudio/best',
            }
            if not is_video:
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3', 'preferredquality': '192',
                }]

            cookie_file = self._find_cookie_file(url)
            if cookie_file:
                ydl_opts['cookiefile'] = cookie_file
            if PROXY_URL:
                ydl_opts['proxy'] = PROXY_URL

            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(
                None, lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=True)
            )
            title = info.get('title', 'video') if info else 'video'

            ext = "mp3" if not is_video else "mp4"
            filepath = os.path.join(self.download_path, f"{filename}.{ext}")
            if not os.path.exists(filepath):
                for f in os.listdir(self.download_path):
                    if f.startswith(filename):
                        filepath = os.path.join(self.download_path, f)
                        break

            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                return {
                    "success": True, "filepath": filepath, "title": title,
                    "uploader": info.get('uploader', '') if info else '',
                    "duration": info.get('duration', 0) if info else 0,
                    "platform": info.get('extractor', 'unknown') if info else 'unknown'
                }
            return {"success": False, "error": "Fayl yuklanmadi"}
        except Exception as e:
            return {"success": False, "error": str(e)[:100]}

    # ==================== ASOSIY ====================
    async def download_video(self, url: str, user_id: int) -> dict:
        if self._is_youtube_url(url):
            logger.info("📺 YouTube video yuklanmoqda...")
            for method in [
                lambda: self.download_with_invidious(url, user_id, is_video=True),
                lambda: self.download_with_piped(url, user_id, is_video=True),
                lambda: self.download_with_ytdlp(url, user_id, is_video=True),
            ]:
                res = await method()
                if res.get("success"):
                    return res
            return {"success": False, "error": "❌ YouTube yuklab bo'lmadi. PO_TOKEN kerak — Railway Variables ga qo'shing."}
        else:
            return await self.download_non_youtube(url, user_id, is_video=True)

    async def download_audio(self, url: str, user_id: int) -> dict:
        if self._is_youtube_url(url):
            logger.info("🎵 YouTube audio yuklanmoqda...")
            for method in [
                lambda: self.download_with_invidious(url, user_id, is_video=False),
                lambda: self.download_with_piped(url, user_id, is_video=False),
                lambda: self.download_with_ytdlp(url, user_id, is_video=False),
            ]:
                res = await method()
                if res.get("success"):
                    return res
            return {"success": False, "error": "❌ YouTube yuklab bo'lmadi. PO_TOKEN kerak."}
        else:
            return await self.download_non_youtube(url, user_id, is_video=False)

    def cleanup_file(self, filepath: str):
        try:
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

    def cleanup_user_files(self, user_id: int):
        try:
            for f in os.listdir(self.download_path):
                if f.startswith(str(user_id)):
                    self.cleanup_file(os.path.join(self.download_path, f))
        except Exception as e:
            logger.error(f"Cleanup user files error: {e}")
