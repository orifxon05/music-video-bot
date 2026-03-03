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
        if not os.path.exists(self.download_path):
            os.makedirs(self.download_path)

    def is_supported_url(self, url: str) -> bool:
        """Link qo'llab-quvvatlanishini tekshirish"""
        supported_domains = [
            'youtube.com', 'youtu.be', 'instagram.com', 'tiktok.com',
            'facebook.com', 'twitter.com', 'x.com', 'soundcloud.com'
        ]
        return any(domain in url.lower() for domain in supported_domains)

    def _find_cookie_file(self, url: str) -> str | None:
        """Platformaga mos cookie faylni topish va absolute path qaytarish"""
        # YouTube uchun
        if any(d in url.lower() for d in ['youtube.com', 'youtu.be']):
            candidates = ['youtube_cookies.txt', 'cookies.txt', 'www.youtube.com_cookies.txt']
        # Instagram uchun
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

    # ==================== 1. INVIDIOUS API ====================
    async def download_with_invidious(self, url: str, user_id: int, is_video: bool = True) -> dict:
        """Invidious API orqali YouTube'dan yuklash (bepul, JWT kerak emas)"""
        
        # YouTube video ID ni ajratib olish
        video_id = self._extract_youtube_id(url)
        if not video_id:
            return {"success": False, "error": "YouTube video ID topilmadi"}
        
        # Ishlaydigan Invidious instansiyalar
        INVIDIOUS_INSTANCES = [
            "https://inv.nadeko.net",
            "https://invidious.nerdvpn.de",
            "https://invidious.jing.rocks",
            "https://invidious.privacyredirect.com",
            "https://iv.datura.network",
            "https://invidious.protokoll-11.dev",
            "https://yt.artemislena.eu",
            "https://invidious.perennialte.ch",
            "https://invidious.snopyta.org",
            "https://invidious.kavin.rocks",
            "https://invidious.flokinet.to",
        ]
        
        async with httpx.AsyncClient(timeout=30.0, verify=False, follow_redirects=True) as client:
            for instance in INVIDIOUS_INSTANCES:
                try:
                    # Video ma'lumotlarini olish
                    api_url = f"{instance}/api/v1/videos/{video_id}"
                    logger.info(f"🔍 Invidious trying: {instance}")
                    
                    resp = await client.get(api_url, headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                    })
                    
                    if resp.status_code != 200:
                        logger.warning(f"⚠️ Invidious {instance}: {resp.status_code}")
                        continue
                    
                    data = resp.json()
                    title = data.get("title", "video")
                    
                    # Download URL tanlash
                    dl_url = None
                    
                    if is_video:
                        # Video formatlarini tekshirish
                        formats = data.get("formatStreams", [])
                        for fmt in formats:
                            if fmt.get("type", "").startswith("video/mp4"):
                                quality = fmt.get("qualityLabel", "")
                                if "720p" in quality or "480p" in quality or "360p" in quality:
                                    dl_url = fmt.get("url")
                                    break
                        # Agar yuqorida topilmasa, birinchi mp4 ni olish
                        if not dl_url:
                            for fmt in formats:
                                if fmt.get("type", "").startswith("video/mp4"):
                                    dl_url = fmt.get("url")
                                    break
                    else:
                        # Audio formatlarini tekshirish
                        adaptive = data.get("adaptiveFormats", [])
                        for fmt in adaptive:
                            if fmt.get("type", "").startswith("audio/"):
                                dl_url = fmt.get("url")
                                break
                    
                    if not dl_url:
                        logger.warning(f"⚠️ Invidious {instance}: download URL topilmadi")
                        continue
                    
                    # Faylni yuklash
                    filename = f"{user_id}_{os.urandom(4).hex()}"
                    ext = "mp4" if is_video else "mp3"
                    filepath = os.path.join(self.download_path, f"{filename}.{ext}")
                    
                    async with client.stream("GET", dl_url) as response:
                        if response.status_code != 200:
                            logger.warning(f"⚠️ Stream download failed: {response.status_code}")
                            continue
                        with open(filepath, "wb") as f:
                            async for chunk in response.aiter_bytes(chunk_size=8192):
                                f.write(chunk)
                    
                    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                        logger.info(f"✅ Invidious success: {instance}")
                        return {
                            "success": True,
                            "filepath": filepath,
                            "title": title,
                            "is_video": is_video
                        }
                    
                except Exception as e:
                    logger.warning(f"❌ Invidious {instance} xato: {str(e)[:100]}")
        
        return {"success": False, "error": "Invidious instansiyalari ishlamadi"}

    # ==================== 2. PIPED API ====================
    async def download_with_piped(self, url: str, user_id: int, is_video: bool = True) -> dict:
        """Piped API orqali YouTube'dan yuklash (bepul, JWT kerak emas)"""
        
        video_id = self._extract_youtube_id(url)
        if not video_id:
            return {"success": False, "error": "YouTube video ID topilmadi"}
        
        PIPED_INSTANCES = [
            "https://pipedapi.kavin.rocks",
            "https://pipedapi.adminforge.de",
            "https://api.piped.projectsegfau.lt",
            "https://pipedapi.in.projectsegfau.lt",
            "https://pipedapi.lunar.icu",
            "https://pipedapi.ryujinx.org",
            "https://pipedapi.leptons.xyz",
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
                        logger.warning(f"⚠️ Piped {instance}: {resp.status_code}")
                        continue
                    
                    data = resp.json()
                    title = data.get("title", "video")
                    
                    dl_url = None
                    
                    if is_video:
                        # Video streamlarini tekshirish
                        streams = data.get("videoStreams", [])
                        # 720p yoki pastroq videoni tanlash
                        for stream in streams:
                            quality = stream.get("quality", "")
                            if stream.get("videoOnly", True) == False:  # Video + Audio
                                if "720p" in quality or "480p" in quality:
                                    dl_url = stream.get("url")
                                    break
                        # Agar topilmasa, birinchisini olish
                        if not dl_url:
                            for stream in streams:
                                if stream.get("videoOnly", True) == False:
                                    dl_url = stream.get("url")
                                    break
                    else:
                        # Audio streamlarini tekshirish
                        streams = data.get("audioStreams", [])
                        # Eng yaxshi sifatli audio
                        best_audio = None
                        best_bitrate = 0
                        for stream in streams:
                            bitrate = stream.get("bitrate", 0)
                            if bitrate > best_bitrate:
                                best_bitrate = bitrate
                                best_audio = stream.get("url")
                        dl_url = best_audio
                    
                    if not dl_url:
                        logger.warning(f"⚠️ Piped {instance}: stream topilmadi")
                        continue
                    
                    # Faylni yuklash
                    filename = f"{user_id}_{os.urandom(4).hex()}"
                    ext = "mp4" if is_video else "mp3"
                    filepath = os.path.join(self.download_path, f"{filename}.{ext}")
                    
                    async with client.stream("GET", dl_url) as response:
                        if response.status_code != 200:
                            continue
                        with open(filepath, "wb") as f:
                            async for chunk in response.aiter_bytes(chunk_size=8192):
                                f.write(chunk)
                    
                    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                        logger.info(f"✅ Piped success: {instance}")
                        return {
                            "success": True,
                            "filepath": filepath,
                            "title": title,
                            "is_video": is_video
                        }
                    
                except Exception as e:
                    logger.warning(f"❌ Piped {instance} xato: {str(e)[:100]}")
        
        return {"success": False, "error": "Piped instansiyalari ishlamadi"}

    # ==================== 2.5 JANATUBE (EXPERIMENTAL) ====================
    async def download_with_janatube(self, url: str, user_id: int, is_video: bool = True) -> dict:
        """Janatube orqali yuklashga urinish (web scraping yondashuvi)"""
        
        video_id = self._extract_youtube_id(url)
        if not video_id:
            return {"success": False, "error": "YouTube video ID topilmadi"}
            
        logger.info(f"🔍 Janatube trying for video: {video_id}")
        
        # Janatube ba'zan YouTube ID orqali to'g'ridan-to'g'ri stream beradi
        # Ammo ko'pincha u shunchaki proxy vazifasini o'taydi.
        # Bu erda biz yt-dlp ni Janatube extractor yoki proxy bilan ishlatishimiz ham mumkin.
        # Lekin biz hozircha shunchaki tartibni saqlab qolamiz.
        
        return {"success": False, "error": "Janatube hozirda avtomatik rejimda qo'llab-quvvatlanmaydi"}

    # ==================== 3. COBALT API (JWT bilan) ====================
    async def download_with_cobalt(self, url: str, user_id: int, is_video: bool = True) -> dict:
        """Cobalt API orqali yuklash (agar JWT token bo'lsa)"""
        
        SERVERS = [
            {"url": "https://cobalt-api.meowing.de", "type": "v11"},
            {"url": "https://capi.3kh0.net", "type": "v11"},
            {"url": "https://cobalt-backend.canine.tools", "type": "v11"},
            {"url": "https://api.cobalt.tools", "type": "v11"}
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

        async with httpx.AsyncClient(timeout=45.0, verify=False) as client:
            for server in SERVERS:
                server_url = server['url']
                try:
                    base_domain = re.search(r'https?://([^/]+)', server_url).group(0)
                    
                    headers = {
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                        "Origin": base_domain,
                        "Referer": base_domain + "/"
                    }

                    logger.info(f"Trying Cobalt server: {server_url}")
                    resp = await client.post(server_url, json=payload, headers=headers)
                    
                    if resp.status_code == 200:
                        data = resp.json()
                        dl_url = data.get("url")
                        
                        if dl_url:
                            logger.info(f"✅ Success from {server_url}, downloading file...")
                            filename = f"{user_id}_{os.urandom(4).hex()}"
                            ext = "mp4" if is_video else "mp3"
                            filepath = os.path.join(self.download_path, f"{filename}.{ext}")
                            
                            async with client.stream("GET", dl_url, follow_redirects=True) as response:
                                if response.status_code != 200:
                                    logger.error(f"❌ Failed to download file from stream URL: {response.status_code}")
                                    continue
                                    
                                with open(filepath, "wb") as f:
                                    async for chunk in response.aiter_bytes():
                                        f.write(chunk)
                            
                            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                                return {
                                    "success": True, 
                                    "filepath": filepath, 
                                    "title": data.get("filename", "audio"),
                                    "is_video": is_video
                                }
                            else:
                                logger.error(f"❌ File downloaded but is empty or missing: {filepath}")
                        else:
                            logger.warning(f"⚠️ Server {server_url} response without URL: {data}")
                    else:
                        resp_text = resp.text[:200] if resp.text else "no body"
                        logger.warning(f"⚠️ Server {server_url} returned status {resp.status_code}: {resp_text}")
                
                except Exception as e:
                    logger.warning(f"❌ Server {server_url} failed: {str(e)[:100]}")
        
        return {"success": False, "error": "Cobalt serverlari ishlamadi"}

    # ==================== 4. YT-DLP (COOKIES BILAN) ====================
    async def download_with_ytdlp(self, url: str, user_id: int, is_video: bool = True) -> dict:
        """yt-dlp orqali yuklash (To'g'rilangan cookies va bypass)"""
        try:
            filename = f"{user_id}_{os.urandom(4).hex()}"
            ext = "mp4" if is_video else "mp3"
            filepath = os.path.join(self.download_path, f"{filename}.{ext}")
            
            ydl_opts = {
                'format': 'bestaudio/best' if not is_video else 'bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'outtmpl': os.path.join(self.download_path, f"{filename}.%(ext)s"),
                'quiet': True,
                'no_warnings': True,
                'nocheckcertificate': True,
                'geo_bypass': True,
                'socket_timeout': 30,
                'retries': 3,
            }

            # COOKIE TEKSHIRISH - To'g'rilangan cookies va bypass
            cookie_file = self._find_cookie_file(url)
            if cookie_file:
                logger.info(f"🍪 Cookie ishlatilmoqda: {cookie_file}")
                ydl_opts['cookiefile'] = cookie_file
                # Cookie bo'lsa ham, bir nechta player_client'larni sinab ko'rish
                ydl_opts['extractor_args'] = {
                    'youtube': {
                        'player_client': ['android', 'ios', 'web'],
                    }
                }
            else:
                logger.warning("⚠️ Cookie fayl topilmadi! YouTube bloklashi mumkin.")
                # Cookie bo'lmasa, bir nechta player_client'larni sinab ko'rish
                ydl_opts['extractor_args'] = {
                    'youtube': {
                        'player_client': ['android', 'ios', 'web'],
                    }
                }

            if not is_video:
                ydl_opts.update({
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                })

            loop = asyncio.get_event_loop()
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=True))
                title = info.get('title', 'video') if info else 'video'
            
            if not is_video:
                filepath = os.path.join(self.download_path, f"{filename}.mp3")

            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                return {"success": True, "filepath": filepath, "title": title}
            
            return {"success": False, "error": "yt-dlp blokda (Cookie kerak)"}
        except Exception as e:
            logger.error(f"yt-dlp error: {e}")
            return {"success": False, "error": f"Blokirovkasi: {str(e)[:100]}"}

    # ==================== ASOSIY YUKLASH FUNKSIYALARI ====================
    def _is_youtube_url(self, url: str) -> bool:
        """YouTube linkmi tekshirish"""
        return any(d in url.lower() for d in ['youtube.com', 'youtu.be'])
    
    def _extract_youtube_id(self, url: str) -> str | None:
        """YouTube video ID ni ajratib olish"""
        patterns = [
            r'(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([a-zA-Z0-9_-]{11})',
            r'^([a-zA-Z0-9_-]{11})$'
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    async def download_video(self, url: str, user_id: int) -> dict:
        """Videoni yuklab olish - Yangilangan ketma-ketlik"""
        
        if self._is_youtube_url(url):
            # YouTube uchun: Invidious -> Piped -> Cobalt -> yt-dlp
            logger.info("📺 YouTube video yuklanmoqda...")
            
            # 1. Invidious
            res = await self.download_with_invidious(url, user_id, is_video=True)
            if res["success"]:
                return res
            
            # 2. Piped
            res = await self.download_with_piped(url, user_id, is_video=True)
            if res["success"]:
                return res
            
            # 3. Cobalt (agar ishlasa)
            res = await self.download_with_cobalt(url, user_id, is_video=True)
            if res["success"]:
                return res
                
            # 4. Janatube (Experimental)
            res = await self.download_with_janatube(url, user_id, is_video=True)
            if res["success"]:
                return res
            
            # 5. yt-dlp (cookie bilan)
            return await self.download_with_ytdlp(url, user_id, is_video=True)
        else:
            # Boshqa platformalar uchun: Cobalt -> yt-dlp
            res = await self.download_with_cobalt(url, user_id, is_video=True)
            if res["success"]:
                return res
            return await self.download_with_ytdlp(url, user_id, is_video=True)

    async def download_audio(self, url: str, user_id: int) -> dict:
        """Audioni yuklab olish - Yangilangan ketma-ketlik"""
        
        if self._is_youtube_url(url):
            # YouTube uchun: Invidious -> Piped -> Cobalt -> yt-dlp
            logger.info("🎵 YouTube audio yuklanmoqda...")
            
            # 1. Invidious
            res = await self.download_with_invidious(url, user_id, is_video=False)
            if res["success"]:
                return res
            
            # 2. Piped
            res = await self.download_with_piped(url, user_id, is_video=False)
            if res["success"]:
                return res
            
            # 3. Cobalt
            res = await self.download_with_cobalt(url, user_id, is_video=False)
            if res["success"]:
                return res
                
            # 4. Janatube (Experimental)
            res = await self.download_with_janatube(url, user_id, is_video=False)
            if res["success"]:
                return res
            
            # 5. yt-dlp
            return await self.download_with_ytdlp(url, user_id, is_video=False)
        else:
            # Boshqa platformalar
            res = await self.download_with_cobalt(url, user_id, is_video=False)
            if res["success"]:
                return res
            return await self.download_with_ytdlp(url, user_id, is_video=False)

    def cleanup_file(self, filepath: str):
        """Faylni o'chirish"""
        try:
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
