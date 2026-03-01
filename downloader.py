"""Video va audio yuklab olish moduli"""
import os
import asyncio
import logging
import yt_dlp
from urllib.parse import urlparse
from config import (
    SUPPORTED_PLATFORMS, 
    DOWNLOAD_PATH, 
    MAX_FILE_SIZE_MB,
    INSTAGRAM_COOKIES_FILE,
    INSTAGRAM_USERNAME,
    INSTAGRAM_PASSWORD,
    PROXY_URL,
    COBALT_API,
    COBALT_ENABLED
)
import requests
import json

# Logging sozlamalari
logger = logging.getLogger(__name__)


class Downloader:
    """Video va audio yuklab oluvchi klass"""
    
    def __init__(self):
        self.download_path = DOWNLOAD_PATH
        os.makedirs(self.download_path, exist_ok=True)
    
    def get_platform(self, url: str) -> str | None:
        """URL dan platformani aniqlash"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower().replace("www.", "")
            
            for platform, domains in SUPPORTED_PLATFORMS.items():
                if any(d in domain for d in domains):
                    return platform
            return None
        except Exception:
            return None
    
    def is_supported_url(self, url: str) -> bool:
        """URL qo'llab-quvvatlanadimi?"""
        return self.get_platform(url) is not None
    
    def _get_instagram_opts(self) -> dict:
        """Instagram uchun maxsus sozlamalar"""
        opts = {}
        
        # 1-usul: Cookie fayli (eng ishonchli)
        cookies_path = os.path.join(os.path.dirname(__file__), INSTAGRAM_COOKIES_FILE)
        if os.path.exists(cookies_path):
            opts['cookiefile'] = cookies_path
            return opts
        
        # 2-usul: Login ma'lumotlari
        if INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD:
            opts['username'] = INSTAGRAM_USERNAME
            opts['password'] = INSTAGRAM_PASSWORD
        
        return opts
    
    async def download_video(self, url: str, user_id: int) -> dict:
        """Video yuklab olish"""
        output_template = os.path.join(
            self.download_path, 
            f"{user_id}_%(id)s.%(ext)s"
        )
        
        ydl_opts = {
            # Eng ishonchli va universal format
            'format': 'best', 
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'geo_bypass': True,
            'noplaylist': True,
            'source_address': '0.0.0.0', 
            'socket_timeout': 60,
            'retries': 10,
            'fragment_retries': 10,
            'extractor_args': {
                'youtube': {
                    'player_client': ['tv', 'mweb', 'android', 'ios'],
                }
            }
        }
        
        # Proxy qo'shish
        if PROXY_URL:
            ydl_opts['proxy'] = PROXY_URL
        
        # YouTube Cookies
        current_dir = os.path.dirname(os.path.abspath(__file__))
        cookies_path = os.path.join(current_dir, 'youtube_cookies.txt')
        
        if os.path.exists(cookies_path):
            logger.info(f"✅ Akkaunt bog'landi (iOS-Match): {cookies_path}")
            ydl_opts['cookiefile'] = cookies_path
            ydl_opts['user_agent'] = 'com.google.ios.youtube/19.29.1 (iPhone16,2; iOS 17.5.1; gzip)'
        else:
            logger.warning("⚠️ Cookies topilmadi!")
            ydl_opts['user_agent'] = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'
        
        # Instagram uchun maxsus sozlamalar qo'shish
        platform = self.get_platform(url)
        if platform == "instagram":
            instagram_opts = self._get_instagram_opts()
            ydl_opts.update(instagram_opts)
        
        # YouTube va Facebook uchun birinchi Cobaltni ishlatamiz (bloklanmaslik uchun)
        is_priority_cobalt = COBALT_ENABLED and (platform in ["youtube", "facebook", "instagram"])
        
        if is_priority_cobalt:
             logger.info(f"⚡ Video: {platform} uchun Cobalt API ishlatilmoqda (Priority)...")
             cobalt_res = await self.download_with_cobalt(url, user_id, is_video=True)
             if cobalt_res.get("success"):
                 return cobalt_res
             # Agar Cobalt o'xshamasa, yt-dlp ga o'tamiz
             logger.warning("⚠️ Cobalt o'xshamadi, yt-dlp ishlatilmoqda...")

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, 
                lambda: self._download_with_yt_dlp(url, ydl_opts)
            )
            
            # Agar muvaffaqiyatsiz bo'lsa va hali Cobalt ishlatilmagan bo'lsa
            if not result.get("success") and not is_priority_cobalt:
                 err = str(result.get("error", "")).lower()
                 if COBALT_ENABLED: 
                     logger.info(f"⚡ Video: yt-dlp xatosi ({err}). Cobalt ishlatilmoqda...")
                     cobalt_res = await self.download_with_cobalt(url, user_id, is_video=True)
                     if cobalt_res.get("success"):
                         return cobalt_res
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def download_with_cobalt(self, url: str, user_id: int, is_video: bool = True) -> dict:
        """Cobalt API v10 orqali yuklab olish (Multi-server fallback)"""
        
        # Yangi va ishlaydigan Cobalt v10 serverlari (2026)
        COBALT_SERVERS = [
            "https://cobalt.instavideosave.com",
            "https://api.cobalt.tools",
            "https://cobalt-api.kwiatekmiki.com",
            "https://cobalt.canine.tools",
            "https://cobalt.mizabot.xyz",
            "https://cobalt.darkness.services",
        ]
        
        # Sarlavhalarni biroz o'zgartiramiz (Ba'zi serverlar uchun)
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        # Agar .env da alohida server ko'rsatilgan bo'lsa
        if COBALT_API and not COBALT_API.endswith("/api/json"):
            if COBALT_API not in COBALT_SERVERS:
                COBALT_SERVERS.insert(0, COBALT_API)

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        
        # Cobalt v10 payload formati
        payload = {
            "url": url,
            "filenameStyle": "basic",
        }

        if is_video:
            payload["videoQuality"] = "720"
            payload["downloadMode"] = "auto"
        else:
            payload["downloadMode"] = "audio"
            payload["audioFormat"] = "mp3"
            payload["audioBitrate"] = "128"
        
        loop = asyncio.get_event_loop()
        last_error = ""

        for base_url in COBALT_SERVERS:
            try:
                # Cobalt v10: POST / (root endpoint)
                api_url = base_url.rstrip("/")
                
                response = await loop.run_in_executor(
                    None,
                    lambda url=api_url: requests.post(url, headers=headers, data=json.dumps(payload), timeout=10)
                )
                
                if response.status_code == 200:
                    data = response.json()
                    status = data.get("status")
                    
                    download_url = None
                    
                    # v10 response formatlari
                    if status in ("tunnel", "redirect"):
                        download_url = data.get("url")
                    elif status == "picker":
                        # Ko'p fayldan birinchisi
                        picker = data.get("picker", [])
                        if picker:
                            download_url = picker[0].get("url")
                    elif status == "error":
                        error_code = data.get("error", {})
                        logger.warning(f"⚠️ Cobalt {api_url} xato: {error_code}")
                        last_error = str(error_code)
                        continue
                    
                    if download_url:
                        # Faylni yuklab olish
                        ext = "mp4" if is_video else "mp3"
                        filepath = os.path.join(self.download_path, f"{user_id}_cobalt_{os.urandom(4).hex()}.{ext}")
                        
                        file_res = await loop.run_in_executor(
                            None,
                            lambda dl_url=download_url: requests.get(dl_url, stream=True, timeout=60)
                        )
                        
                        if file_res.status_code == 200:
                            with open(filepath, 'wb') as f:
                                for chunk in file_res.iter_content(chunk_size=8192):
                                    if chunk:
                                        f.write(chunk)
                            
                            # Fayl hajmini tekshirish
                            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                                logger.info(f"✅ Cobalt v10 orqali yuklandi: {api_url}")
                                return {
                                    "success": True,
                                    "filepath": filepath,
                                    "title": data.get("filename", "Video" if is_video else "Audio"),
                                    "duration": 0,
                                    "uploader": "Cobalt API",
                                    "platform": self.get_platform(url),
                                }
                
                # Xatoni yozamiz
                error_text = response.text[:200] if response.text else "No content"
                logger.warning(f"⚠️ Cobalt {api_url} xato: {response.status_code} - {error_text}")
                last_error = f"{response.status_code} - {error_text}"
                
            except Exception as e:
                logger.warning(f"⚠️ Cobalt {base_url} ulanish xatosi: {e}")
                last_error = str(e)
                continue
        
        logger.error(f"❌ Barcha Cobalt serverlari ishlamadi. Oxirgi xato: {last_error}")
        return {"success": False, "error": f"Serverlar band. Xato: {last_error[:50]}"}
    
    async def download_audio(self, url: str, user_id: int) -> dict:
        """Audio yuklab olish - TEZ"""
        output_template = os.path.join(
            self.download_path, 
            f"{user_id}_%(id)s_audio.%(ext)s"
        )
        
        # Tez va sifatli format - m4a Player uchun eng yaxshisi
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'geo_bypass': True,
            'noplaylist': True,
            'source_address': '0.0.0.0',
            'socket_timeout': 60,
            'extractor_args': {
                'youtube': {
                    'player_client': ['ios', 'android', 'mweb', 'web'],
                }
            }
        }
        
        # Akkaunt orqali kirish
        current_dir = os.path.dirname(os.path.abspath(__file__))
        cookies_path = os.path.join(current_dir, 'youtube_cookies.txt')
        
        if os.path.exists(cookies_path):
            ydl_opts['cookiefile'] = cookies_path
            ydl_opts['user_agent'] = 'com.google.ios.youtube/19.29.1 (iPhone16,2; iOS 17.5.1; gzip)'
        
        # Instagram uchun maxsus sozlamalar qo'shish
        platform = self.get_platform(url)
        if platform == "instagram":
            instagram_opts = self._get_instagram_opts()
            ydl_opts.update(instagram_opts)
        
        # YouTube va Facebook uchun birinchi Cobaltni ishlatamiz (Audio)
        platform = self.get_platform(url)
        is_priority_cobalt = COBALT_ENABLED and (platform in ["youtube", "facebook", "instagram"])
        
        if is_priority_cobalt:
             logger.info(f"⚡ Audio: {platform} uchun Cobalt API ishlatilmoqda (Priority)...")
             cobalt_res = await self.download_with_cobalt(url, user_id, is_video=False)
             if cobalt_res.get("success"):
                 return cobalt_res
             logger.warning("⚠️ Cobalt o'xshamadi, yt-dlp ishlatilmoqda...")

        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, 
                lambda: self._download_audio_simple(url, ydl_opts)
            )
            
            # Agar yt-dlp xato bergan bo'lsa va hali Cobalt ishlatilmagan bo'lsa
            if not result.get("success") and not is_priority_cobalt:
                err = str(result.get("error", "")).lower()
                if COBALT_ENABLED: # Har qanday xatoda Cobaltni sinab ko'rish
                    logger.info(f"⚡ Audio: yt-dlp xatosi ({err}). Cobalt ishlatilmoqda...")
                    cobalt_res = await self.download_with_cobalt(url, user_id, is_video=False)
                    if cobalt_res.get("success"):
                        return cobalt_res
            
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _download_audio_simple(self, url: str, ydl_opts: dict) -> dict:
        """Oddiy audio yuklab olish"""
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                if info is None:
                    return {"success": False, "error": "Ma'lumot olishda xatolik"}
                
                # Fayl yo'lini topish
                filepath = None
                
                # 1. requested_downloads dan (eng ishonchli)
                if 'requested_downloads' in info and info['requested_downloads']:
                    filepath = info['requested_downloads'][0].get('filepath')
                
                # 2. prepare_filename dan
                if not filepath:
                    try:
                        filepath = ydl.prepare_filename(info)
                    except:
                        pass
                
                # 3. outtmpl dan taxmin qilish
                if not filepath:
                    video_id = info.get('id', 'unknown')
                    ext = info.get('ext', 'm4a')
                    # ext bo'lmasligi mumkin agar merge bo'lsa
                    filepath = ydl_opts['outtmpl'] % {'id': video_id, 'ext': ext}
                
                # Fayl mavjudligini tekshirish
                if filepath and os.path.exists(filepath):
                    return {
                        "success": True,
                        "filepath": filepath,
                        "title": info.get('title', 'Audio'),
                        "duration": info.get('duration', 0),
                        "uploader": info.get('uploader', ''),
                    }
                
                # 4. Downloads papkasidan qidirish (oxirgi chora)
                video_id = info.get('id', '')
                if video_id:
                    for filename in os.listdir(self.download_path):
                        if video_id in filename:
                            fpath = os.path.join(self.download_path, filename)
                            # Fayl bo'sh emasligini tekshirish
                            if os.path.exists(fpath) and os.path.getsize(fpath) > 0:
                                return {
                                    "success": True,
                                    "filepath": fpath,
                                    "title": info.get('title', 'Audio'),
                                    "duration": info.get('duration', 0),
                                    "uploader": info.get('uploader', ''),
                                }
                
                return {"success": False, "error": "Fayl yuklandi lekin topilmadi"}
                    
        except Exception as e:
            # Agar birinchi urinishda format xatosi bo'lsa, oddiyroq sozlamalar bilan sinab ko'ramiz
            if "format" in str(e).lower() or "client" in str(e).lower():
                try:
                    logger.info("🔄 Qayta urinish: Oddiy format bilan...")
                    simple_opts = ydl_opts.copy()
                    simple_opts['format'] = 'ba/best'
                    if 'extractor_args' in simple_opts:
                        del simple_opts['extractor_args']
                    
                    with yt_dlp.YoutubeDL(simple_opts) as ydl:
                        info = ydl.extract_info(url, download=True)
                        if info:
                            # Fayl yo'lini topish
                            filepath = ydl.prepare_filename(info)
                            if os.path.exists(filepath):
                                return {
                                    "success": True,
                                    "filepath": filepath,
                                    "title": info.get('title', 'Audio'),
                                    "duration": info.get('duration', 0),
                                    "uploader": info.get('uploader', ''),
                                }
                except Exception as retry_e:
                    return {"success": False, "error": f"Retry xatosi: {str(retry_e)[:50]}"}
            
            return {"success": False, "error": f"Xatolik: {str(e)[:100]}"}
    
    def _download_audio_yt_dlp(self, url: str, ydl_opts: dict, output_template: str) -> dict:
        """Audio yuklab olish - maxsus"""
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                if info is None:
                    return {"success": False, "error": "Video ma'lumotlarini olishda xatolik"}
                
                # Fayl yo'lini topish - turli variantlarni tekshirish
                filepath = None
                
                # 1. requested_downloads dan
                if 'requested_downloads' in info and info['requested_downloads']:
                    filepath = info['requested_downloads'][0].get('filepath')
                
                # 2. MP3 fayl bormi
                if not filepath or not os.path.exists(filepath):
                    mp3_path = output_template + '.mp3'
                    if os.path.exists(mp3_path):
                        filepath = mp3_path
                
                # 3. Boshqa formatlar
                if not filepath or not os.path.exists(filepath):
                    for ext in ['mp3', 'm4a', 'webm', 'opus', 'ogg']:
                        test_path = output_template + '.' + ext
                        if os.path.exists(test_path):
                            filepath = test_path
                            break
                
                # 4. Downloads papkasidan qidirish
                if not filepath or not os.path.exists(filepath):
                    video_id = info.get('id', '')
                    for filename in os.listdir(self.download_path):
                        if video_id in filename and '_audio' in filename:
                            filepath = os.path.join(self.download_path, filename)
                            break
                
                if filepath and os.path.exists(filepath):
                    return {
                        "success": True,
                        "filepath": filepath,
                        "title": info.get('title', 'Audio'),
                        "duration": info.get('duration', 0),
                        "uploader": info.get('uploader', ''),
                    }
                else:
                    return {"success": False, "error": "Audio fayl yaratilmadi"}
                    
        except yt_dlp.utils.DownloadError as e:
            return {"success": False, "error": f"Yuklab olishda xatolik"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _download_with_yt_dlp(self, url: str, ydl_opts: dict) -> dict:
        """yt-dlp bilan yuklab olish"""
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                if info is None:
                    return {"success": False, "error": "Video ma'lumotlarini olishda xatolik"}
                
                # Fayl yo'lini topish
                filepath = None
                if 'requested_downloads' in info and info['requested_downloads']:
                    filepath = info['requested_downloads'][0].get('filepath')
                
                if not filepath:
                    ext = info.get('ext', 'mp4')
                    filepath = ydl_opts['outtmpl'] % {'id': info['id'], 'ext': ext}
                
                # Fayl hajmini tekshirish
                if filepath and os.path.exists(filepath):
                    file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
                    if file_size_mb > MAX_FILE_SIZE_MB:
                        os.remove(filepath)
                        return {"success": False, "error": f"Fayl juda katta ({file_size_mb:.1f}MB)"}
                    
                    return {
                        "success": True,
                        "filepath": filepath,
                        "title": info.get('title', 'Nomalum'),
                        "duration": info.get('duration', 0),
                        "uploader": info.get('uploader', 'Nomalum'),
                        "thumbnail": info.get('thumbnail'),
                        "platform": self.get_platform(url),
                    }
                else:
                    return {"success": False, "error": "Fayl yuklanmadi"}
                    
        except Exception as e:
            # Format xatosi bo'lsa qayta urinish
            if "format" in str(e).lower() or "client" in str(e).lower():
                try:
                    logger.info("🔄 Video qayta urinish: Oddiy rejimda...")
                    simple_opts = ydl_opts.copy()
                    simple_opts['format'] = 'bestvideo+bestaudio/best'
                    if 'extractor_args' in simple_opts:
                        del simple_opts['extractor_args']
                    
                    with yt_dlp.YoutubeDL(simple_opts) as ydl:
                        info = ydl.extract_info(url, download=True)
                        if info:
                            filepath = ydl.prepare_filename(info)
                            if os.path.exists(filepath):
                                return {
                                    "success": True,
                                    "filepath": filepath,
                                    "title": info.get('title', 'Nomalum'),
                                    "duration": info.get('duration', 0),
                                    "uploader": info.get('uploader', 'Nomalum'),
                                    "thumbnail": info.get('thumbnail'),
                                    "platform": self.get_platform(url),
                                }
                except:
                    pass
            return {"success": False, "error": str(e)}
    
    def cleanup_file(self, filepath: str):
        """Faylni o'chirish"""
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception:
            pass
    
    def cleanup_user_files(self, user_id: int):
        """Foydalanuvchi fayllarini o'chirish"""
        try:
            for filename in os.listdir(self.download_path):
                if filename.startswith(f"{user_id}_"):
                    filepath = os.path.join(self.download_path, filename)
                    os.remove(filepath)
        except Exception:
            pass
