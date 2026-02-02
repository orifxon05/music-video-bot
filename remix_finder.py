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
                "remixes": remixes,
                "covers": covers
            }
        except Exception as e:
            logger.error(f"Remix finding error: {e}")
            return {"success": False, "error": str(e)}

    async def _search_type(self, query: str, filter_type: str, limit: int) -> list:
        try:
            # Synchronous call
            results = self.yt.search(query, filter=filter_type, limit=limit)
            
            formatted = []
            for item in results:
                video_id = item.get("videoId")
                if not video_id:
                    continue
                    
                title = item.get("title", "Nomalum")
                artists = item.get("artists", [])
                artist_name = artists[0].get("name", "") if artists else ""
                
                url = f"https://www.youtube.com/watch?v={video_id}"
                
                formatted.append({
                    "title": f"{artist_name} - {title}" if artist_name else title,
                    "url": url,
                    "duration": item.get("duration", "0:00"),
                    "channel": artist_name or "YT Music",
                    "id": video_id,
                    "views": "N/A" # YTMusic search doesn't always return views cleanly in search
                })
            return formatted
        except Exception as e:
            logger.error(f"Inner search error ({query}): {e}")
            return []

    def format_results(self, results: dict) -> str:
        """Natijalarni formatlash"""
        if not results.get('success'):
            return f"❌ {results.get('error', 'Qidirishda xatolik')}"
        
        text = f"🔄 **Remix va Cover versiyalari**\n\n"
        text += f"🎵 **Asl qo'shiq:** {results.get('title', 'Nomalum')}\n"
        text += f"👤 **Ijrochi:** {results.get('artist', 'Nomalum')}\n\n"
        
        # Remixlar
        remixes = results.get('remixes', [])
        if remixes:
            text += "🎧 **Remix versiyalari:**\n"
            for i, remix in enumerate(remixes, 1):
                text += f"{i}. [{remix['title']}]({remix['url']})\n"
                text += f"   ⏱ {remix['duration']}\n"
            text += "\n"
        else:
            text += "🎧 **Remix:** Topilmadi\n\n"
        
        # Coverlar
        covers = results.get('covers', [])
        if covers:
            text += "🎤 **Cover versiyalari:**\n"
            for i, cover in enumerate(covers, 1):
                text += f"{i}. [{cover['title']}]({cover['url']})\n"
                text += f"   ⏱ {cover['duration']}\n"
        else:
            text += "🎤 **Cover:** Topilmadi"
        
        return text
