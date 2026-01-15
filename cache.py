"""Kesh tizimi - yuklangan fayllarni saqlash"""
import os
import json
import hashlib
from datetime import datetime, timedelta


class FileCache:
    """Telegram file_id keshi"""
    
    def __init__(self, cache_file: str = "cache.json"):
        self.cache_file = cache_file
        self.cache = self._load_cache()
        self.max_age_hours = 24  # 24 soat saqlash
    
    def _load_cache(self) -> dict:
        """Keshni yuklash"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
        except:
            pass
        return {"audio": {}, "video": {}}
    
    def _save_cache(self):
        """Keshni saqlash"""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f)
        except:
            pass
    
    def _get_url_hash(self, url: str) -> str:
        """URL dan hash yaratish"""
        return hashlib.md5(url.encode()).hexdigest()[:16]
    
    def get_audio(self, url: str) -> str | None:
        """Audio file_id olish"""
        url_hash = self._get_url_hash(url)
        
        if url_hash in self.cache.get("audio", {}):
            data = self.cache["audio"][url_hash]
            
            # Muddati o'tganmi tekshirish
            cached_time = datetime.fromisoformat(data.get("time", "2000-01-01"))
            if datetime.now() - cached_time < timedelta(hours=self.max_age_hours):
                return data.get("file_id")
            else:
                # Eskirgan - o'chirish
                del self.cache["audio"][url_hash]
                self._save_cache()
        
        return None
    
    def save_audio(self, url: str, file_id: str, title: str = ""):
        """Audio file_id saqlash"""
        url_hash = self._get_url_hash(url)
        
        self.cache["audio"][url_hash] = {
            "file_id": file_id,
            "title": title,
            "time": datetime.now().isoformat(),
        }
        self._save_cache()
    
    def get_video(self, url: str) -> str | None:
        """Video file_id olish"""
        url_hash = self._get_url_hash(url)
        
        if url_hash in self.cache.get("video", {}):
            data = self.cache["video"][url_hash]
            
            cached_time = datetime.fromisoformat(data.get("time", "2000-01-01"))
            if datetime.now() - cached_time < timedelta(hours=self.max_age_hours):
                return data.get("file_id")
            else:
                del self.cache["video"][url_hash]
                self._save_cache()
        
        return None
    
    def save_video(self, url: str, file_id: str, title: str = ""):
        """Video file_id saqlash"""
        url_hash = self._get_url_hash(url)
        
        self.cache["video"][url_hash] = {
            "file_id": file_id,
            "title": title,
            "time": datetime.now().isoformat(),
        }
        self._save_cache()
    
    def clear_old(self):
        """Eski keshlarni tozalash"""
        now = datetime.now()
        
        for cache_type in ["audio", "video"]:
            to_delete = []
            for url_hash, data in self.cache.get(cache_type, {}).items():
                cached_time = datetime.fromisoformat(data.get("time", "2000-01-01"))
                if now - cached_time > timedelta(hours=self.max_age_hours):
                    to_delete.append(url_hash)
            
            for url_hash in to_delete:
                del self.cache[cache_type][url_hash]
        
        self._save_cache()


# Global kesh
cache = FileCache()
