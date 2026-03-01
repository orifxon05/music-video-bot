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

    def is_supported_url(self, url: str) -> bool:
        """Link qo'llab-quvvatlanishini tekshirish"""
        supported_domains = [
            'youtube.com', 'youtu.be', 'instagram.com', 'tiktok.com',
            'facebook.com', 'twitter.com', 'x.com', 'soundcloud.com'
        ]
        return any(domain in url.lower() for domain in supported_domains)

    async def download_with_cobalt(self, url: str, user_id: int, is_video: bool = True) -> dict:
        """Ishonchli Cobalt va muqobil API serverlari orqali yuklash"""
        
        # 2026-yilda ishlayotgan eng ishonchli yangi serverlar (v11+)
        SERVERS = [
            {"url": "https://cobalt-api.meowing.de/api/json", "type": "v11"},
            {"url": "https://cobalt-backend.canine.tools/api/json", "type": "v11"},
            {"url": "https://kityune.imput.net/api/json", "type": "v11"},
            {"url": "https://sunny.imput.net/api/json", "type": "v11"},
            {"url": "https://blossom.imput.net/api/json", "type": "v11"},
            {"url": "https://nachos.imput.net/api/json", "type": "v11"},
            {"url": "https://capi.3kh0.net/api/json", "type": "v11"},
            {"url": "https://api.cobalt.tools/api/json", "type": "v11"}
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

        async with httpx.AsyncClient(timeout=45.0, verify=False) as client:
            for server in SERVERS:
                server_url = server['url']
                try:
                    logger.info(f"Trying server: {server_url}")
                    resp = await client.post(server_url, json=payload, headers=headers)
                    
                    if resp.status_code == 200:
                        data = resp.json()
                        dl_url = None
                        status = data.get("status")
                        
                        # Variantlar: stream, redirect, success (v10/v11)
                        if status in ["stream", "redirect", "success"]:
                            dl_url = data.get("url")
                        elif not status and data.get("url"): # Ba'zi APIlar status qaytarmasligi mumkin
                            dl_url = data.get("url")
                            
                        if dl_url:
                            logger.info(f"✅ Success from {server_url}, downloading file...")
                            # Faylni serverga yuklab olamiz
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
                        logger.warning(f"⚠️ Server {server_url} returned status {resp.status_code}: {resp.text[:200]}")
                
                except Exception as e:
                    logger.warning(f"❌ Server {server_url} failed with error: {str(e)[:150]}")
        
        return {"success": False, "error": "Barcha serverlar band yoki ishlamayapti (Server timeout yoki blok)"}

    async def download_audio(self, url: str, user_id: int) -> dict:
        """Audioni yuklab olish (Cobalt -> yt-dlp fallback)"""
        res = await self.download_with_cobalt(url, user_id, is_video=False)
        if res["success"]:
            return res
        return await self.download_with_ytdlp(url, user_id, is_video=False)

    async def download_video(self, url: str, user_id: int) -> dict:
        """Videoni yuklab olish"""
        res = await self.download_with_cobalt(url, user_id, is_video=True)
        if res["success"]:
            return res
        return await self.download_with_ytdlp(url, user_id, is_video=True)

    async def download_with_ytdlp(self, url: str, user_id: int, is_video: bool = True) -> dict:
        """yt-dlp orqali yuklash"""
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
            
            if not is_video:
                filepath = os.path.join(self.download_path, f"{filename}.mp3")

            if os.path.exists(filepath):
                return {"success": True, "filepath": filepath, "title": "downloaded"}
            
            return {"success": False, "error": "Fayl yuklanmadi"}
        except Exception as e:
            logger.error(f"yt-dlp error: {e}")
            return {"success": False, "error": str(e)}

    def cleanup_file(self, filepath: str):
        """Faylni o'chirish"""
        try:
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
