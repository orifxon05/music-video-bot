"""Qo'shiq qidirish moduli - nom bo'yicha"""
import asyncio
import os
import yt_dlp


class MusicSearcher:
    """Qo'shiq nomi bo'yicha qidirish (yt-dlp ishlatadi - eng barqaror)"""
    
    def __init__(self):
        self.max_results = 10
        self.ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'skip_download': True,
            'source_address': '0.0.0.0', # IPv4
            'nocheckcertificate': True,
            'extractor_args': {
                'youtube': {
                    'player_client': ['ios', 'android', 'mweb', 'web'],
                }
            }
        }
        
        # Cookies va iOS User-Agent (Search uchun ham bir xil bo'lishi shart)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        cookies_path = os.path.join(current_dir, 'youtube_cookies.txt')
        if os.path.exists(cookies_path):
            self.ydl_opts['cookiefile'] = cookies_path
            self.ydl_opts['user_agent'] = 'com.google.ios.youtube/19.29.1 (iPhone16,2; iOS 17.5.1; gzip)'
    
    async def search_by_name(self, query: str) -> dict:
        """Qo'shiq nomini qidirish"""
        try:
            query = query.strip()
            if not query:
                return {"success": False, "error": "Bo'sh qidiruv"}
            
            # yt-dlp search query
            search_query = f"ytsearch{self.max_results}:{query}"
            
            loop = asyncio.get_event_loop()
            results = await loop.run_in_executor(
                None,
                lambda: self._extract_info(search_query)
            )
            
            if results and 'entries' in results:
            # Asosiy qidiruv
            results = self.yt.search(query, filter="songs", limit=limit)
            
            # Agar qo'shiqlar topilmasa, videolar qidirib ko'ramiz
            if not results:
                results = self.yt.search(query, filter="videos", limit=limit)
                
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
            logger.error(f"Search error: {e}")
            return {"success": False, "error": str(e)}
    
    def _extract_info(self, query: str):
    def _format_duration(self, seconds) -> str:
        if not seconds: return "Nomalum"
        seconds = int(seconds)
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}:{secs:02d}"

    def _format_views(self, views) -> str:
        if not views: return "0"
        views = int(views)
        if views >= 1000000:
            return f"{views/1000000:.1f}M"
        if views >= 1000:
            return f"{views/1000:.1f}K"
        return str(views)
