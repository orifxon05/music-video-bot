"""Musiqa qidirish moduli (Qidiruv aniqligi oshirildi)"""
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
        """Musiqa nomi bo'yicha qidirish (Aniqlik oshirilgan versiya)"""
        if not query or len(query.strip()) < 2:
            return {"success": False, "error": "Qidiruv so'zi kamida 2 ta belgidan iborat bo'lishi kerak"}

        query = query.strip()
        results = []
        
        # 1. YTMusic (Advanced Search)
        if self.yt:
            try:
                # Naqadar kutilgan natija chiqishi uchun filter'siz qidiramiz
                # Bu orqali videolar, klaxlar va qo'shiqlar birga chiqadi
                raw_results = self.yt.search(query, filter=None, limit=limit + 5)
                
                for item in raw_results:
                    v_id = item.get("videoId")
                    if not v_id: continue
                    
                    category = item.get("resultType", "unknown")
                    # Faqat qo'shiq va videolarni olamiz
                    if category not in ["song", "video"]: continue
                    
                    title = item.get("title", "Nomalum")
                    artists = item.get("artists", [])
                    artist_name = artists[0].get("name", "") if artists else ""
                    duration = item.get("duration", "0:00")
                    
                    results.append({
                        "videoId": v_id,
                        "title": title,
                        "artist": artist_name,
                        "duration": duration,
                        "score": 10 if category == "song" else 8 # Qo'shiqlar baland balda
                    })
                    
                # Agar natija oz bo'lsa, yana urinib ko'ramiz
                if len(results) < 3:
                     song_results = self.yt.search(query, filter="songs", limit=5)
                     for item in song_results:
                         if not item.get("videoId"): continue
                         results.append({
                            "videoId": item.get("videoId"),
                            "title": item.get("title", "Nomalum"),
                            "artist": (item.get("artists", [{}])[0].get("name", "")),
                            "duration": item.get("duration", "0:00"),
                            "score": 9
                         })

            except Exception as e:
                logger.warning(f"YTMusic advanced search error: {e}")

        # 2. yt-dlp (Fallback)
        if len(results) < 2:
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
                            "duration": self._format_seconds(entry.get("duration", 0)),
                            "score": 5
                        })
            except Exception as e:
                logger.error(f"yt-dlp search error: {e}")

        # Dublikatlarni tozalash va Saralash
        seen_ids = set()
        final_results = []
        
        # Avval yuqori balli natijalarni tartiblaymiz
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        
        for item in results:
            v_id = item["videoId"]
            if v_id in seen_ids: continue
            seen_ids.add(v_id)
            
            title = item["title"]
            artist = item["artist"]
            
            # Agar sarlavhada artist nomi yo'q bo'lsa, qo'shib qo'yamiz
            full_title = f"{artist} - {title}" if artist and artist.lower() not in title.lower() else title
            
            final_results.append({
                "title": full_title,
                "url": f"https://www.youtube.com/watch?v={v_id}",
                "duration": item["duration"],
                "id": v_id
            })

        if final_results:
            return {"success": True, "results": final_results[:limit]}
        return {"success": False, "error": "Hech narsa topilmadi"}
