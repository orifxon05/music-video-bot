"""Musiqa aniqlash moduli (Shazam-like)"""
import os
import asyncio
from shazamio import Shazam
from pydub import AudioSegment


class MusicRecognizer:
    """Shazam orqali musiqa aniqlash"""
    
    def __init__(self):
        self.shazam = Shazam()
    
    async def recognize_from_file(self, filepath: str) -> dict:
        """Fayl orqali musiqa aniqlash"""
        try:
            # Agar fayl mp3 emas bo'lsa, convert qilish
            if not filepath.endswith('.mp3'):
                filepath = await self._convert_to_mp3(filepath)
            
            # Shazam orqali aniqlash
            result = await self.shazam.recognize(filepath)
            
            if result and 'track' in result:
                track = result['track']
                return {
                    "success": True,
                    "title": track.get('title', 'Noma\'lum'),
                    "artist": track.get('subtitle', 'Noma\'lum'),
                    "album": self._get_album(track),
                    "genre": self._get_genre(track),
                    "year": self._get_year(track),
                    "cover_art": self._get_cover_art(track),
                    "spotify_url": self._get_spotify_url(track),
                    "apple_music_url": self._get_apple_music_url(track),
                    "shazam_url": track.get('url'),
                    "raw_data": track,
                }
            else:
                return {"success": False, "error": "Musiqa topilmadi"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def _convert_to_mp3(self, filepath: str) -> str:
        """Audio faylni MP3 ga convert qilish"""
        try:
            output_path = filepath.rsplit('.', 1)[0] + '_converted.mp3'
            
            await asyncio.to_thread(
                self._do_convert, filepath, output_path
            )
            
            return output_path
        except Exception:
            return filepath
    
    def _do_convert(self, input_path: str, output_path: str):
        """Asinxron convert"""
        try:
            audio = AudioSegment.from_file(input_path)
            audio.export(output_path, format='mp3')
        except Exception:
            pass
    
    def _get_album(self, track: dict) -> str:
        """Albom nomini olish"""
        try:
            sections = track.get('sections', [])
            for section in sections:
                if section.get('type') == 'SONG':
                    metadata = section.get('metadata', [])
                    for meta in metadata:
                        if meta.get('title') == 'Album':
                            return meta.get('text', 'Noma\'lum')
        except Exception:
            pass
        return 'Noma\'lum'
    
    def _get_genre(self, track: dict) -> str:
        """Janrni olish"""
        try:
            genres = track.get('genres', {})
            primary = genres.get('primary', '')
            return primary if primary else 'Noma\'lum'
        except Exception:
            return 'Noma\'lum'
    
    def _get_year(self, track: dict) -> str:
        """Yilni olish"""
        try:
            sections = track.get('sections', [])
            for section in sections:
                if section.get('type') == 'SONG':
                    metadata = section.get('metadata', [])
                    for meta in metadata:
                        if meta.get('title') == 'Released':
                            return meta.get('text', '')
        except Exception:
            pass
        return ''
    
    def _get_cover_art(self, track: dict) -> str | None:
        """Cover rasmini olish"""
        try:
            images = track.get('images', {})
            return images.get('coverart') or images.get('background')
        except Exception:
            return None
    
    def _get_spotify_url(self, track: dict) -> str | None:
        """Spotify havolasini olish"""
        try:
            providers = track.get('hub', {}).get('providers', [])
            for provider in providers:
                if provider.get('type') == 'SPOTIFY':
                    actions = provider.get('actions', [])
                    if actions:
                        return actions[0].get('uri')
        except Exception:
            pass
        return None
    
    def _get_apple_music_url(self, track: dict) -> str | None:
        """Apple Music havolasini olish"""
        try:
            providers = track.get('hub', {}).get('providers', [])
            for provider in providers:
                if provider.get('type') == 'APPLEMUSIC':
                    actions = provider.get('actions', [])
                    if actions:
                        return actions[0].get('uri')
        except Exception:
            pass
        return None
    
    def format_result(self, result: dict) -> str:
        """Natijani formatlash"""
        if not result.get('success'):
            return f"😔 {result.get('error', 'Musiqa topilmadi')}"
        
        text = f"""🎵 **Musiqa Topildi!**

🎤 **Qo'shiq:** {result['title']}
👤 **Ijrochi:** {result['artist']}
💿 **Albom:** {result['album']}
🎭 **Janr:** {result['genre']}"""

        if result['year']:
            text += f"\n📅 **Yil:** {result['year']}"
        
        text += "\n\n🔗 **Havolalar:**"
        
        if result.get('spotify_url'):
            text += f"\n• [Spotify]({result['spotify_url']})"
        
        if result.get('apple_music_url'):
            text += f"\n• [Apple Music]({result['apple_music_url']})"
        
        if result.get('shazam_url'):
            text += f"\n• [Shazam]({result['shazam_url']})"
        
        text += "\n\n👉 @SavemuzikVideoBot"
        
        return text
