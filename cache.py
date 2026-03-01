"""Kesh tizimi - PostgreSQL bazaga saqlash"""
import hashlib
from database import db


class FileCache:
    """Telegram file_id keshi (PostgreSQL bazada)"""
    
    def _get_url_hash(self, url: str) -> str:
        """URL dan hash yaratish"""
        return hashlib.md5(url.encode()).hexdigest()[:16]
    
    def get_audio(self, url: str) -> str | None:
        """Audio file_id olish"""
        url_hash = self._get_url_hash(url)
        return db.get_file_cache(url_hash, "audio")
    
    def save_audio(self, url: str, file_id: str, title: str = ""):
        """Audio file_id saqlash"""
        url_hash = self._get_url_hash(url)
        db.save_file_cache(url_hash, "audio", file_id, title)
    
    def get_video(self, url: str) -> str | None:
        """Video file_id olish"""
        url_hash = self._get_url_hash(url)
        return db.get_file_cache(url_hash, "video")
    
    def save_video(self, url: str, file_id: str, title: str = ""):
        """Video file_id saqlash"""
        url_hash = self._get_url_hash(url)
        db.save_file_cache(url_hash, "video", file_id, title)
    
    def clear_old(self):
        """Eski keshlarni tozalash"""
        db.clear_old_cache()


# Global kesh
cache = FileCache()
