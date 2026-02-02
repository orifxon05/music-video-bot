"""Remix va Cover qidiruv moduli"""
import logging
from ytmusicapi import YTMusic

logger = logging.getLogger(__name__)

class RemixFinder:
    def __init__(self):
        self.yt = YTMusic()
    
    async def find_all_versions(self, title: str, artist: str) -> dict:
        """Remix va Cover versiyalarini topish"""
        try:
            query = f"{title} {artist}"
            remixes = await self._search_type(f"{query} remix", "songs", limit=10)
            covers = await self._search_type(f"{query} cover", "videos", limit=10)
            
            return {
                "success": True,
                "title": title,
                "artist": artist,
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
                    "title": video.get('title', 'Noma\'lum'),
                    "url": video.get('link', ''),
                    "duration": video.get('duration', ''),
                    "views": video.get('viewCount', {}).get('short', ''),
                    "channel": video.get('channel', {}).get('name', ''),
                    "thumbnail": video.get('thumbnails', [{}])[0].get('url', ''),
                    "published": video.get('publishedTime', ''),
                })
            
            return videos
        except Exception:
            return []
    
    def format_results(self, results: dict) -> str:
        """Natijalarni formatlash"""
        if not results.get('success'):
            return f"❌ {results.get('error', 'Qidirishda xatolik')}"
        
        text = f"""🔄 **Remix va Cover versiyalari**

🎵 **Asl qo'shiq:** {results['title']}
👤 **Ijrochi:** {results['artist']}

"""
        
        # Remixlar
        remixes = results.get('remixes', [])
        if remixes:
            text += "🎧 **Remix versiyalari:**\n"
            for i, remix in enumerate(remixes, 1):
                text += f"{i}. [{remix['title']}]({remix['url']})\n"
                text += f"   👁 {remix['views']} • ⏱ {remix['duration']}\n"
            text += "\n"
        else:
            text += "🎧 **Remix:** Topilmadi\n\n"
        
        # Coverlar
        covers = results.get('covers', [])
        if covers:
            text += "🎤 **Cover versiyalari:**\n"
            for i, cover in enumerate(covers, 1):
                text += f"{i}. [{cover['title']}]({cover['url']})\n"
                text += f"   👁 {cover['views']} • ⏱ {cover['duration']}\n"
        else:
            text += "🎤 **Cover:** Topilmadi"
        
        return text
