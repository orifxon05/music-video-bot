"""Musiqa qidirish moduli (ytmusicapi)"""
import logging
from ytmusicapi import YTMusic

logger = logging.getLogger(__name__)

class MusicSearcher:
    """Musiqa qidirish klassi (YTMusic API)"""
    
    def __init__(self):
        self.yt = YTMusic() # API ni initsializatsiya qilish

    async def search_by_name(self, query: str, limit: int = 10) -> dict:
        """Musiqa nomi bo'yicha qidirish (YouTube Music)"""
        try:
            query = query.strip()
            if not query:
                return {"success": False, "error": "Bo'sh qidiruv"}

            # 1. Asosiy qidiruv (Qo'shiqlar)
            try:
                results = self.yt.search(query, filter="songs", limit=limit)
            except Exception as e:
                logger.error(f"YTMusic songs search error: {e}")
                results = []
            
            # 2. Agar qo'shiqlar topilmasa, videolar qidirib ko'ramiz
            if not results:
                try:
                    results = self.yt.search(query, filter="videos", limit=limit)
                except Exception as e:
                    logger.error(f"YTMusic videos search error: {e}")
                    results = []
                
            formatted_results = []
            
            for item in results:
                # VideoID olish
                video_id = item.get("videoId")
                if not video_id:
                    continue
                    
                title = item.get("title", "Nomalum")
                
                # Artist nomini olish
                artists = item.get("artists", [])
                artist_name = ""
                if artists:
                    artist_name = artists[0].get("name", "")
                
                # Davomiylik
                duration = item.get("duration", "0:00")
                
                # Link
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
