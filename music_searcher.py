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
            'source_address': '0.0.0.0', # IPv4 majburiy
            'nocheckcertificate': True,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios'],
                }
            }
        }
        
        # Cookies qo'shish (Search uchun ham kerak)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        cookies_path = os.path.join(current_dir, 'youtube_cookies.txt')
        if os.path.exists(cookies_path):
            self.ydl_opts['cookiefile'] = cookies_path
            self.ydl_opts['user_agent'] = 'com.google.android.youtube/17.31.35 (Linux; U; Android 12; GB) Mozilla/5.0'
    
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
                formatted_results = []
                for entry in results['entries']:
                    if not entry: continue
                    
                    formatted_results.append({
                        "title": entry.get('title', 'Nomalum'),
                        "url": entry.get('url') or entry.get('webpage_url') or f"https://www.youtube.com/watch?v={entry.get('id')}",
                        "duration": self._format_duration(entry.get('duration')),
                        "views": self._format_views(entry.get('view_count')),
                        "channel": entry.get('uploader', 'Nomalum'),
                        "id": entry.get('id', ''),
                    })
                
                if formatted_results:
                    return {
                        "success": True,
                        "query": query,
                        "results": formatted_results,
                        "count": len(formatted_results),
                    }
            
            return {"success": False, "error": "Hech narsa topilmadi"}
                
        except Exception as e:
            print(f"DEBUG: yt-dlp search error: {e}")
            return {"success": False, "error": str(e)}
    
    def _extract_info(self, query: str):
        with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
            return ydl.extract_info(query, download=False)

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
