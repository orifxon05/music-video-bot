"""Musiqa qidirish moduli (ytmusicapi)"""
import logging
from ytmusicapi import YTMusic

logger = logging.getLogger(__name__)

class MusicSearcher:
    """Musiqa qidirish klassi (YTMusic API)"""
    
    def __init__(self):
        self.yt = YTMusic() # API ni initsializatsiya qilish

    async def search_by_name(self, query: str, limit: int = 10) -> dict:
        """Musiqa nomi bo'yicha qidirish (YouTube Music with yt-dlp fallback)"""
        try:
            query = query.strip()
            if not query:
                return {"success": False, "error": "Bo'sh qidiruv"}

            results = []
            
            # 1. YTMusic orqali qidib ko'rish
            try:
                results = self.yt.search(query, filter="songs", limit=limit)
            except Exception as e:
                if "429" in str(e):
                    logger.warning(f"⚠️ YTMusic Rate Limit (429). yt-dlp ishlatilmoqda...")
                else:
                    logger.error(f"YTMusic search error: {e}")
            
            # 2. Agar YTMusic topmasa yoki xato bersa, yt-dlp orqali qidirish
            if not results:
                try:
                    import yt_dlp
                    import asyncio
                    
                    ydl_opts = {
                        'format': 'bestaudio/best',
                        'quiet': True,
                        'no_warnings': True,
                        'extract_flat': True,
                    }
                    
                    # yt-dlp search query
                    search_query = f"ytsearch{limit}:{query}"
                    
                    def _yt_dlp_search():
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            return ydl.extract_info(search_query, download=False)
                    
                    loop = asyncio.get_event_loop()
                    search_results = await loop.run_in_executor(None, _yt_dlp_search)
                    
                    if search_results and 'entries' in search_results:
                        for entry in search_results['entries']:
                            if not entry: continue
                            results.append({
                                "videoId": entry.get("id"),
                                "title": entry.get("title"),
                                "artists": [{"name": entry.get("uploader", "")}],
                                "duration": self._format_seconds(entry.get("duration", 0))
                            })
                except Exception as ydl_e:
                    logger.error(f"yt-dlp search fallback error: {ydl_e}")

            formatted_results = []
            for item in results:
                video_id = item.get("videoId")
                if not video_id: continue
                    
                title = item.get("title", "Nomalum")
                artists = item.get("artists", [])
                artist_name = artists[0].get("name", "") if artists else ""
                duration = item.get("duration", "0:00")
                url = f"https://www.youtube.com/watch?v={video_id}"
                
                formatted_results.append({
                    "title": f"{artist_name} - {title}" if artist_name else title,
                    "url": url,
                    "duration": duration,
                    "id": video_id
                })
            
            if formatted_results:
                return {"success": True, "results": formatted_results}
            else:
                return {"success": False, "error": "Hech narsa topilmadi"}
                
        except Exception as e:
            logger.error(f"Global search error: {e}")
            return {"success": False, "error": str(e)}

    def _format_seconds(self, seconds):
        if not seconds: return "0:00"
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"
