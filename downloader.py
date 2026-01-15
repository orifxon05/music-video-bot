"""Video va audio yuklab olish moduli"""
import os
import asyncio
import yt_dlp
from urllib.parse import urlparse
from config import SUPPORTED_PLATFORMS, DOWNLOAD_PATH, MAX_FILE_SIZE_MB


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
    
    async def download_video(self, url: str, user_id: int) -> dict:
        """Video yuklab olish"""
        output_template = os.path.join(
            self.download_path, 
            f"{user_id}_%(id)s.%(ext)s"
        )
        
        ydl_opts = {
            'format': 'best[filesize<50M]/best',
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'socket_timeout': 30,
        }
        
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, 
                lambda: self._download_with_yt_dlp(url, ydl_opts)
            )
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def download_audio(self, url: str, user_id: int) -> dict:
        """Audio yuklab olish (video'dan)"""
        output_template = os.path.join(
            self.download_path, 
            f"{user_id}_%(id)s_audio.%(ext)s"
        )
        
        # FFmpeg'siz - to'g'ridan-to'g'ri audio yuklab olish
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'outtmpl': output_template,
            'quiet': False,
            'no_warnings': False,
            'extract_flat': False,
            'socket_timeout': 120,
            'retries': 3,
            # FFmpeg postprocessor yo'q - to'g'ridan-to'g'ri saqlash
        }
        
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, 
                lambda: self._download_audio_simple(url, ydl_opts)
            )
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
                
                if 'requested_downloads' in info and info['requested_downloads']:
                    filepath = info['requested_downloads'][0].get('filepath')
                
                if not filepath:
                    # Template dan yaratish
                    video_id = info.get('id', 'unknown')
                    ext = info.get('ext', 'm4a')
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
                
                # Downloads papkasidan qidirish
                video_id = info.get('id', '')
                if video_id:
                    for filename in os.listdir(self.download_path):
                        if video_id in filename:
                            filepath = os.path.join(self.download_path, filename)
                            if os.path.exists(filepath):
                                return {
                                    "success": True,
                                    "filepath": filepath,
                                    "title": info.get('title', 'Audio'),
                                    "duration": info.get('duration', 0),
                                    "uploader": info.get('uploader', ''),
                                }
                
                return {"success": False, "error": "Fayl topilmadi"}
                    
        except Exception as e:
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
                    
        except yt_dlp.utils.DownloadError as e:
            return {"success": False, "error": f"Yuklab olishda xatolik"}
        except Exception as e:
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
