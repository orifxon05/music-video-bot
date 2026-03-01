"""Musiqa qidirish moduli (ytmusicapi + yt-dlp fallback)"""
import logging
import asyncio
import yt_dlp
from ytmusicapi import YTMusic

logger = logging.getLogger(__name__)

class MusicSearcher:
    """Musiqa qidirish klassi"""
    
    def __init__(self):
        try:
            self.yt = YTMusic()
        except Exception as e:
            logger.error(f"YTMusic init error: {e}")
            self.yt = None

    def _format_seconds(self, seconds):
        if not seconds: return "0:00"
        try:
            seconds = int(seconds)
            m, s = divmod(seconds, 60)
            h, m = divmod(m, 60)
            if h > 0:
                return f"{h}:{m:02d}:{s:02d}"
            return f"{m}:{s:02d}"
        except:
            return "0:00"

    async def search_by_name(self, query: str, limit: int = 10) -> dict:
        """Musiqa nomi bo'yicha qidirish"""
        query = str(query).strip()
        if not query:
            return {"success": False, "error": "Bo'sh qidiruv"}

        results = []
        
        # 1. YTMusic (Songs)
        if self.yt:
            try:
                raw_results = self.yt.search(query, filter="songs", limit=limit)
                for item in raw_results:
                    if not item.get("videoId"): continue
                    artists = item.get("artists", [])
                    artist_name = artists[0].get("name", "") if artists else ""
                    results.append({
                        "videoId": item.get("videoId"),
                        "title": item.get("title", "Nomalum"),
                        "artist": artist_name,
                        "duration": item.get("duration", "0:00")
                    })
            except Exception as e:
                logger.warning(f"YTMusic search error: {e}")

        # 2. yt-dlp (Fallback) - Agar YTMusic topmasa yoki xato bersa
        if not results:
            try:
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': True,
                }
                search_query = f"ytsearch{limit}:{query}"
                
                loop = asyncio.get_event_loop()
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    data = await loop.run_in_executor(None, lambda: ydl.extract_info(search_query, download=False))
                    
                if data and 'entries' in data:
                    for entry in data['entries']:
                        if not entry: continue
                        results.append({
                            "videoId": entry.get("id"),
                            "title": entry.get("title", "Nomalum"),
                            "artist": entry.get("uploader", ""),
                            "duration": self._format_seconds(entry.get("duration", 0))
                        })
            except Exception as e:
                logger.error(f"yt-dlp search error: {e}")

        # Natijalarni formatlash
        formatted = []
        for item in results:
            v_id = item.get("videoId")
            if not v_id: continue
            
            title = item.get("title", "Nomalum")
            artist = item.get("artist", "")
            
            formatted.append({
                "title": f"{artist} - {title}" if artist else title,
                "url": f"https://www.youtube.com/watch?v={v_id}",
                "duration": item.get("duration", "0:00"),
                "id": v_id
            })

        if formatted:
            return {"success": True, "results": formatted}
        return {"success": False, "error": "Hech narsa topilmadi"}
