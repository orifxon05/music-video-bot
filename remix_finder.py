"""Remix va Cover versiyalarini topish moduli"""
import asyncio
from youtubesearchpython import VideosSearch


class RemixFinder:
    """YouTube'dan remix va cover topish"""
    
    def __init__(self):
        self.max_results = 8
    
    async def find_remixes(self, title: str, artist: str) -> dict:
        """Remix versiyalarini topish"""
        try:
            search_query = f"{title} {artist} remix audio"
            results = await self._search_youtube(search_query)
            
            return {
                "success": True,
                "type": "remix",
                "query": search_query,
                "results": results,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def find_covers(self, title: str, artist: str) -> dict:
        """Cover versiyalarini topish"""
        try:
            search_query = f"{title} {artist} cover audio"
            results = await self._search_youtube(search_query)
            
            return {
                "success": True,
                "type": "cover",
                "query": search_query,
                "results": results,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def find_all_versions(self, title: str, artist: str) -> dict:
        """Remix va Cover'larni birga topish"""
        try:
            # Parallel qidirish
            remix_task = self.find_remixes(title, artist)
            cover_task = self.find_covers(title, artist)
            
            remix_results, cover_results = await asyncio.gather(
                remix_task, cover_task
            )
            
            return {
                "success": True,
                "title": title,
                "artist": artist,
                "remixes": remix_results.get("results", []),
                "covers": cover_results.get("results", []),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
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
                if 'shorts' in video.get('link', '').lower():
                    continue
                
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
