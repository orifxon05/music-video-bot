import logging
import asyncio
import os
import httpx
import yt_dlp
import re
from config import DOWNLOAD_PATH, PROXY_URL, COBALT_API, MAX_FILE_SIZE_MB

logger = logging.getLogger(__name__)

class Downloader:
    def __init__(self):
        self.download_path = DOWNLOAD_PATH
        if not os.path.exists(self.download_path):
            os.makedirs(self.download_path)

    async def download_with_cobalt(self, url: str, user_id: int, is_video: bool = True) -> dict:
        """Ishonchli Cobalt va muqobil API serverlari orqali yuklash"""
        
        # 2026-yilda ishlayotgan ishonchli serverlar
        SERVERS = [
            {"url": "https://cobalt.canine.tools/api/json", "type": "v10"},
            {"url": "https://api.cobalt.tools/api/json", "type": "v10"},
            {"url": "https://cobalt.mizabot.xyz/api/json", "type": "v10"},
            {"url": "https://cobalt-api.kwiatekmiki.com/api/json", "type": "v10"},
            {"url": "https://imput.net/api/json", "type": "v10"}
        ]
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Origin": "https://cobalt.tools",
            "Referer": "https://cobalt.tools/"
        }

        payload = {
            "url": url,
            "videoQuality": "720",
            "audioFormat": "mp3",
            "filenamePattern": "basic",
            "isAudioOnly": not is_video,
            "disableMetadata": False,
            "audioBitrate": "128"
        }

        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            for server in SERVERS:
                try:
                    logger.info(f"Trying server: {server['url']}")
                    resp = await client.post(server['url'], json=payload, headers=headers)
                    
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("status") == "stream" or data.get("status") == "redirect":
                            return {"success": True, "url": data.get("url"), "title": data.get("filename", "audio")}
                        elif data.get("status") == "success":
                            return {"success": True, "url": data.get("url"), "title": "audio"}
                    
                    logger.warning(f"Server {server['url']} error: {resp.status_code}")
                except Exception as e:
                    logger.warning(f"Server {server['url']} failed: {str(e)[:100]}")
        
        return {"success": False, "error": "Barcha serverlar band yoki ishlamayapti"}

    async def download_audio(self, url: str, user_id: int) -> dict:
        """Audioni yuklab olish (Cobalt -> yt-dlp fallback)"""
        # 1. Cobalt orqali harakat
        res = await self.download_with_cobalt(url, user_id, is_video=False)
        if res["success"]:
            return res

        # 2. yt-dlp fallback (Bloklangan bo'lishi mumkin, lekin baribir urinib ko'ramiz)
        return await self.download_with_ytdlp(url, user_id, is_video=False)

    async def download_video(self, url: str, user_id: int) -> dict:
        """Videoni yuklab olish"""
        res = await self.download_with_cobalt(url, user_id, is_video=True)
        if res["success"]:
            return res
        
        return await self.download_with_ytdlp(url, user_id, is_video=True)

    async def download_with_ytdlp(self, url: str, user_id: int, is_video: bool = True) -> dict:
        """yt-dlp orqali yuklash (Hozircha YouTube bloklashi mumkin)"""
        try:
            filename = f"{user_id}_{os.urandom(4).hex()}"
            ext = "mp4" if is_video else "mp3"
            filepath = os.path.join(self.download_path, f"{filename}.{ext}")
            
            ydl_opts = {
                'format': 'bestaudio/best' if not is_video else 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'outtmpl': os.path.join(self.download_path, f"{filename}.%(ext)s"),
                'quiet': True,
                'no_warnings': True,
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
                await loop.run_in_executor(None, lambda: ydl.download([url]))
            
            # Agar mp3 bo'lsa, extension o'zgargan bo'lishi mumkin
            if not is_video:
                filepath = os.path.join(self.download_path, f"{filename}.mp3")

            if os.path.exists(filepath):
                return {"success": True, "path": filepath, "title": "downloaded"}
            
            return {"success": False, "error": "Fayl yuklanmadi"}
        except Exception as e:
            logger.error(f"yt-dlp error: {e}")
            return {"success": False, "error": str(e)}
