import logging
import asyncio
import os
import httpx
import yt_dlp
import re
import json
from config import DOWNLOAD_PATH, PROXY_URL, COBALT_API, MAX_FILE_SIZE_MB
import pathlib

logger = logging.getLogger(__name__)

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
                abs_path = pathlib.Path(cookie_file).resolve()
                logger.info(f"🍪 Cookie fayli topildi: {abs_path}")
                return str(abs_path)
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

    # ==================== 1. INVIDIOUS API ====================
    async def download_with_invidious(self, url: str, user_id: int, is_video: bool = True) -> dict:
        video_id = self._extract_youtube_id(url)
        if not video_id:
            return {"success": False, "error": "YouTube video ID topilmadi"}

        INVIDIOUS_INSTANCES = [
            "https://inv.nadeko.net",
            "https://invidious.nerdvpn.de",
            "https://invidious.privacyredirect.com",
            "https://iv.datura.network",
            "https://yt.artemislena.eu",
            "https://invidious.perennialte.ch",
            "https://invidious.kavin.rocks",
            "https://invidious.flokinet.to",
        ]

        async with httpx.AsyncClient(timeout=30.0, verify=False, follow_redirects=True) as client:
            for instance in INVIDIOUS_INSTANCES:
                try:
                    api_url = f"{instance}/api/v1/videos/{video_id}"
                    logger.info(f"🔍 Invidious trying: {instance}")

                    resp = await client.get(api_url, headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    })

                    if resp.status_code != 200:
                        continue

                    data = resp.json()
                    title = data.get("title", "video")
                    dl_url = None

                    if is_video:
                        formats = data.get("formatStreams", [])
                        for fmt in formats:
                            if fmt.get("type", "").startswith("video/mp4"):
                                quality = fmt.get("qualityLabel", "")
                                if any(q in quality for q in ["720p", "480p", "360p"]):
                                    dl_url = fmt.get("url")
                                    break
                        if not dl_url:
                            for fmt in formats:
                                if fmt.get("type", "").startswith("video/mp4"):
                                    dl_url = fmt.get("url")
                                    break
                    else:
                        adaptive = data.get("adaptiveFormats", [])
                        for fmt in adaptive:
                            if fmt.get("type", "").startswith("audio/"):
                                dl_url = fmt.get("url")
                                break

                    if not dl_url:
                        continue

                    filename = f"{user_id}_{os.urandom(4).hex()}"
                    ext = "mp4" if is_video else "mp3"
                    filepath = os.path.join(self.download_path, f"{filename}.{ext}")

                    async with client.stream("GET", dl_url) as response:
                        if response.status_code != 200:
                            continue
                        with open(filepath, "wb") as f:
                            async for chunk in response.aiter_bytes(chunk_size=8192):
                                f.write(chunk)

                    if os.path.exists(filepath) and os.path.getsize(filepath) > 10_000:
                        logger.info(f"✅ Invidious success: {instance}")
                        return {"success": True, "filepath": filepath, "title": title, "is_video": is_video}

                except Exception as e:
                    logger.warning(f"❌ Invidious {instance}: {str(e)[:80]}")

        return {"success": False, "error": "Invidious instansiyalari ishlamadi"}

    # ==================== 2. PIPED API ====================
    async def download_with_piped(self, url: str, user_id: int, is_video: bool = True) -> dict:
        video_id = self._extract_youtube_id(url)
        if not video_id:
            return {"success": False, "error": "YouTube video ID topilmadi"}

        PIPED_INSTANCES = [
            "https://pipedapi.kavin.rocks",
            "https://pipedapi.adminforge.de",
            "https://api.piped.projectsegfau.lt",
            "https://pipedapi.lunar.icu",
        ]

        async with httpx.AsyncClient(timeout=30.0, verify=False, follow_redirects=True) as client:
            for instance in PIPED_INSTANCES:
                try:
                    api_url = f"{instance}/streams/{video_id}"
                    logger.info(f"🔍 Piped trying: {instance}")

                    resp = await client.get(api_url, headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    })

                    if resp.status_code != 200:
                        continue

                    data = resp.json()
                    title = data.get("title", "video")
                    dl_url = None

                    if is_video:
                        streams = data.get("videoStreams", [])
                        for stream in streams:
                            if not stream.get("videoOnly", True):
                                quality = stream.get("quality", "")
                                if "720p" in quality or "480p" in quality:
                                    dl_url = stream.get("url")
                                    break
                        if not dl_url:
                            for stream in streams:
                                if not stream.get("videoOnly", True):
                                    dl_url = stream.get("url")
                                    break
                    else:
                        streams = data.get("audioStreams", [])
                        best_bitrate = 0
                        for stream in streams:
                            bitrate = stream.get("bitrate", 0)
                            if bitrate > best_bitrate:
                                best_bitrate = bitrate
                                dl_url = stream.get("url")

                    if not dl_url:
                        continue

                    filename = f"{user_id}_{os.urandom(4).hex()}"
                    ext = "mp4" if is_video else "mp3"
                    filepath = os.path.join(self.download_path, f"{filename}.{ext}")

                    async with client.stream("GET", dl_url) as response:
                        if response.status_code != 200:
                            continue
                        with open(filepath, "wb") as f:
                            async for chunk in response.aiter_bytes(chunk_size=8192):
                                f.write(chunk)

                    if os.path.exists(filepath) and os.path.getsize(filepath) > 10_000:
                        logger.info(f"✅ Piped success: {instance}")
                        return {"success": True, "filepath": filepath, "title": title, "is_video": is_video}

                except Exception as e:
                    logger.warning(f"❌ Piped {instance}: {str(e)[:80]}")

        return {"success": False, "error": "Piped instansiyalari ishlamadi"}

    # ==================== 3. COBALT API ====================
    async def download_with_cobalt(self, url: str, user_id: int, is_video: bool = True) -> dict:
        SERVERS = [
            "https://cobalt-api.meowing.de",
            "https://capi.3kh0.net",
            "https://cobalt-backend.canine.tools",
            "https://api.cobalt.tools",
        ]

        payload = {
            "url": url,
            "videoQuality": "720",
            "audioFormat": "mp3",
            "filenamePattern": "basic",
            "isAudioOnly": not is_video,
            "downloadMode": "audio" if not is_video else "auto",
            "audioBitrate": "128"
        }

        async with httpx.AsyncClient(timeout=45.0, verify=False, follow_redirects=True) as client:
            for server_url in SERVERS:
                try:
                    base_domain = re.search(r'https?://[^/]+', server_url).group(0)
                    headers = {
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Origin": base_domain,
                        "Referer": base_domain + "/"
                    }

                    logger.info(f"🔍 Cobalt trying: {server_url}")
                    resp = await client.post(server_url, json=payload, headers=headers)

                    if resp.status_code != 200:
                        continue

                    data = resp.json()
                    dl_url = data.get("url")
                    if not dl_url:
                        continue

                    filename = f"{user_id}_{os.urandom(4).hex()}"
                    ext = "mp4" if is_video else "mp3"
                    filepath = os.path.join(self.download_path, f"{filename}.{ext}")

                    async with client.stream("GET", dl_url) as response:
                        if response.status_code != 200:
                            continue
                        with open(filepath, "wb") as f:
                            async for chunk in response.aiter_bytes():
                                f.write(chunk)

                    if os.path.exists(filepath) and os.path.getsize(filepath) > 10_000:
                        logger.info(f"✅ Cobalt success: {server_url}")
                        return {
                            "success": True,
                            "filepath": filepath,
                            "title": data.get("filename", "audio"),
                            "is_video": is_video
                        }

                except Exception as e:
                    logger.warning(f"❌ Cobalt {server_url}: {str(e)[:80]}")

        return {"success": False, "error": "Cobalt serverlari ishlamadi"}

    # ==================== 4. YT-DLP ====================
    async def download_with_ytdlp(self, url: str, user_id: int, is_video: bool = True) -> dict:
        try:
            filename = f"{user_id}_{os.urandom(4).hex()}"
            filepath_template = os.path.join(self.download_path, f"{filename}.%(ext)s")

            ydl_opts = {
                'outtmpl': filepath_template,
                'quiet': True,
                'no_warnings': True,
                'nocheckcertificate': True,
                'geo_bypass': True,
                'socket_timeout': 30,
                'retries': 3,
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android', 'ios', 'web'],
                    }
                },
            }

            if is_video:
                ydl_opts['format'] = 'bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4]/best'
            else:
                ydl_opts['format'] = 'bestaudio/best'
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]

            cookie_file = self._find_cookie_file(url)
            if cookie_file:
                ydl_opts['cookiefile'] = cookie_file
                logger.info(f"✅ Cookie ishlatilmoqda: {cookie_file}")

            if PROXY_URL:
                ydl_opts['proxy'] = PROXY_URL
                logger.info(f"🔀 Proxy ishlatilmoqda: {PROXY_URL}")

            loop = asyncio.get_event_loop()
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
                title = info.get('title', 'video') if info else 'video'
                uploader = info.get('uploader', '') if info else ''
                duration = info.get('duration', 0) if info else 0
                platform = info.get('extractor', 'unknown') if info else 'unknown'

            # Yuklangan faylni topish
            ext = "mp3" if not is_video else "mp4"
            filepath = os.path.join(self.download_path, f"{filename}.{ext}")

            # Agar aniq fayl yo'q bo'lsa, papkada qidirish
            if not os.path.exists(filepath):
                for f in os.listdir(self.download_path):
                    if f.startswith(filename):
                        filepath = os.path.join(self.download_path, f)
                        break

            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                logger.info(f"✅ yt-dlp success: {filepath}")
                return {
                    "success": True,
                    "filepath": filepath,
                    "title": title,
                    "uploader": uploader,
                    "duration": duration,
                    "platform": platform,
                }

            return {"success": False, "error": "yt-dlp: fayl yaratilmadi"}

        except Exception as e:
            error_str = str(e)
            logger.error(f"yt-dlp error: {error_str[:150]}")
            return {"success": False, "error": f"yt-dlp xatosi: {error_str[:100]}"}

    # ==================== ASOSIY FUNKSIYALAR ====================
    async def download_video(self, url: str, user_id: int) -> dict:
        """Videoni yuklab olish — fallback zanjiri"""
        if self._is_youtube_url(url):
            logger.info("📺 YouTube video yuklanmoqda...")
            for method in [
                lambda: self.download_with_invidious(url, user_id, is_video=True),
                lambda: self.download_with_piped(url, user_id, is_video=True),
                lambda: self.download_with_cobalt(url, user_id, is_video=True),
                lambda: self.download_with_ytdlp(url, user_id, is_video=True),
            ]:
                res = await method()
                if res.get("success"):
                    return res
            return {"success": False, "error": "Barcha usullar ishlamadi. YouTube bu serverni bloklaган bo'lishi mumkin."}
        else:
            for method in [
                lambda: self.download_with_cobalt(url, user_id, is_video=True),
                lambda: self.download_with_ytdlp(url, user_id, is_video=True),
            ]:
                res = await method()
                if res.get("success"):
                    return res
            return {"success": False, "error": "Video yuklab bo'lmadi"}

    async def download_audio(self, url: str, user_id: int) -> dict:
        """Audioni yuklab olish — fallback zanjiri"""
        if self._is_youtube_url(url):
            logger.info("🎵 YouTube audio yuklanmoqda...")
            for method in [
                lambda: self.download_with_invidious(url, user_id, is_video=False),
                lambda: self.download_with_piped(url, user_id, is_video=False),
                lambda: self.download_with_cobalt(url, user_id, is_video=False),
                lambda: self.download_with_ytdlp(url, user_id, is_video=False),
            ]:
                res = await method()
                if res.get("success"):
                    return res
            return {"success": False, "error": "Barcha usullar ishlamadi."}
        else:
            for method in [
                lambda: self.download_with_cobalt(url, user_id, is_video=False),
                lambda: self.download_with_ytdlp(url, user_id, is_video=False),
            ]:
                res = await method()
                if res.get("success"):
                    return res
            return {"success": False, "error": "Audio yuklab bo'lmadi"}

    def cleanup_file(self, filepath: str):
        """Faylni xavfsiz o'chirish"""
        try:
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
                logger.debug(f"🗑 Fayl o'chirildi: {filepath}")
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

    def cleanup_user_files(self, user_id: int):
        """Foydalanuvchiga tegishli barcha fayllarni o'chirish"""
        try:
            for f in os.listdir(self.download_path):
                if f.startswith(str(user_id)):
                    self.cleanup_file(os.path.join(self.download_path, f))
        except Exception as e:
            logger.error(f"Cleanup user files error: {e}")
