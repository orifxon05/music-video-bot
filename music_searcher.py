"""Qo'shiq qidirish moduli - nom bo'yicha"""
import asyncio
from youtubesearchpython import VideosSearch


class MusicSearcher:
    """Qo'shiq nomi bo'yicha qidirish"""
    
    def __init__(self):
        self.max_results = 15  # Ko'proq natija olamiz
    
    async def search_by_name(self, query: str) -> dict:
        """Qo'shiq nomini qidirish"""
        try:
            query = query.strip()
            if not query:
                return {"success": False, "error": "Bo'sh qidiruv"}
            
            # YouTube'da qidirish - qo'shimchalarsiz, YouTube o'zi aqlli
            print(f"DEBUG: Searching YouTube for: {query}")
            results = await self._search_youtube(query)
            
            if results:
                print(f"DEBUG: Found {len(results)} results")
                return {
                    "success": True,
                    "query": query,
                    "results": results,
                    "count": len(results),
                }
            else:
                print(f"DEBUG: No results found for: {query}")
                return {"success": False, "error": "Hech narsa topilmadi"}
                
        except Exception as e:
            print(f"DEBUG: Search error: {e}")
            return {"success": False, "error": str(e)}
    
    async def search_song(self, title: str, artist: str = "") -> dict:
        """Qo'shiq va ijrochini qidirish"""
        query = f"{artist} {title}".strip() if artist else title
        return await self.search_by_name(query)
    
    async def _search_youtube(self, query: str) -> list:
        """YouTube'da qidirish"""
        try:
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                lambda: self._do_search(query)
            )
            return results
        except Exception:
            return []
    
    def _do_search(self, query: str) -> list:
        """Qidirish bajarish"""
        try:
            search = VideosSearch(query, limit=self.max_results)
            raw_results = search.result()
            
            videos = []
            for video in raw_results.get('result', []):
                videos.append({
                    "title": video.get('title', 'Nomalum'),
                    "url": video.get('link', ''),
                    "duration": video.get('duration', ''),
                    "views": video.get('viewCount', {}).get('short', ''),
                    "channel": video.get('channel', {}).get('name', ''),
                    "thumbnail": video.get('thumbnails', [{}])[0].get('url', ''),
                    "published": video.get('publishedTime', ''),
                    "id": video.get('id', ''),
                })
            
            return videos
        except Exception:
            return []
    
    def format_results(self, results: dict) -> str:
        """Natijalarni formatlash"""
        if not results.get('success'):
            return f"❌ {results.get('error', 'Qidirishda xatolik')}"
        
        text = f"""🔍 **Qidiruv: "{results['query']}"**

🎵 **Topildi: {results['count']} ta natija**

"""
        
        for i, item in enumerate(results.get('results', []), 1):
            text += f"""**{i}. {item['title']}**
👤 {item['channel']} • ⏱ {item['duration']} • 👁 {item['views']}
🔗 /download_{item['id']}

"""
        
        return text.strip()
