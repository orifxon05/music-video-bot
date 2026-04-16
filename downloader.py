import logging
import asyncio
import os
import httpx
import yt_dlp
import re
import pathlib
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from config import DOWNLOAD_PATH, PROXY_URL, MAX_FILE_SIZE_MB

logger = logging.getLogger(__name__)

# ==================== PO_TOKEN SOZLAMASI ====================
PO_TOKEN    = os.getenv("PO_TOKEN", "")
VISITOR_DATA = os.getenv("VISITOR_DATA", "")

# ==================== SPOTIFY SOZLAMASI ====================
# Railway Environment Variables ga qo'shing:
#   SPOTIFY_CLIENT_ID     — developer.spotify.com dan
#   SPOTIFY_CLIENT_SECRET — developer.spotify.com dan
SPOTIFY_CLIENT_ID     = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")


def _get_spotify_client() -> spotipy.Spotify | None:
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        logger.warning("⚠️ SPOTIFY_CLIENT_ID yoki SPOTIFY_CLIENT_SECRET topilmadi")
        return None
    try:
        auth = SpotifyClientCredentials(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET,
        )
        return spotipy.Spotify(auth_manager=auth)
    except Exception as e:
        logger.error(f"Spotify client xatosi: {e}")
        return None


class Downloader:
    def __init__(self):
        self.download_path = DOWNLOAD_PATH
        os.makedirs(self.download_path, exist_ok=True)

    # ==================== URL YORDAMCHI METODLAR ====================

    def is_supported_url(self, url: str) -> bool:
        supported_domains = [
            'youtube.com', 'youtu.be', 'instagram.com', 'tiktok.com',
            'facebook.com', 'twitter.com', 'x.com', 'soundcloud.com',
            'spotify.com',
        ]
        return any(domain in url.lower() for domain in supported_domains)

    def _is_youtube_url(self, url: str) -> bool:
        return any(d in url.lower() for d in ['youtube.com', 'youtu.be'])

    def _is_spotify_url(self, url: str) -> bool:
        return 'open.spotify.com' in url.lower()

    def _spotify_url_type(self, url: str) -> str | None:
        """track / album / playlist yoki None"""
        match = re.search(r'open\.spotify\.com/(track|album|playlist)/', url)
        return match.group(1) if match else None

    def _extract_spotify_id(self, url: str) -> str | None:
        match = re.search(r'open\.spotify\.com/(?:track|album|playlist)/([A-Za-z0-9]+)', url)
        return match.group(1) if match else None

    def _extract_youtube_id(self, url: str) -> str | None:
        patterns = [
            r'(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([a-zA-Z0-9_-]{11})',
            r'^([a-zA-Z0-9_-]{11})$',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _find_cookie_file(self, url: str) -> str | None:
        if any(d in url.lower() for d in ['youtube.com', 'youtu.be']):
            candidates = ['youtube_cookies.txt', 'cookies.txt', 'www.youtube.com_cookies.txt']
        elif 'instagram.com' in url.lower():
            candidates = ['www.instagram.com_cookies.txt', 'instagram_cookies.txt', 'cookies.txt']
        else:
            candidates = ['cookies.txt']
        for cookie_file in candidates:
            if os.path.exists(cookie_file):
                return str(pathlib.Path(cookie_file).resolve())
        return None

    # ==================== SPOTIFY METODLARI ====================

    def _spotify_track_to_search_query(self, track: dict) -> str:
        """Spotify track dict dan YouTube qidiruv so'rovini yasaydi"""
        name    = track.get('name', '')
        artists = ', '.join(a['name'] for a in track.get('artists', []))
        return f"{artists} - {name}"

    async def _spotify_get_tracks(self, url: str) -> list[dict]:
        """
        Spotify URL dan track ro'yxatini qaytaradi.
        Har bir element: {'title': str, 'artist': str, 'duration_ms': int, 'search_query': str}
        """
        sp = _get_spotify_client()
        if not sp:
            return []

        url_type = self._spotify_url_type(url)
        spotify_id = self._extract_spotify_id(url)
        if not spotify_id:
            return []

        loop = asyncio.get_running_loop()
        tracks = []

        try:
            if url_type == 'track':
                track = await loop.run_in_executor(None, lambda: sp.track(spotify_id))
                tracks = [track]

            elif url_type == 'album':
                album = await loop.run_in_executor(None, lambda: sp.album(spotify_id))
                tracks = album.get('tracks', {}).get('items', [])
                # album tracks da full track ob'ekti yo'q, artistlarni albomdan olamiz
                album_artists = album.get('artists', [])
                for t in tracks:
                    if not t.get('artists'):
                        t['artists'] = album_artists

            elif url_type == 'playlist':
                results = await loop.run_in_executor(None, lambda: sp.playlist_items(spotify_id))
                tracks = [item['track'] for item in results.get('items', []) if item.get('track')]

        except Exception as e:
            logger.error(f"Spotify metadata xatosi: {e}")
            return []

        output = []
        for t in tracks:
            if not t:
                continue
            output.append({
                'title':        t.get('name', 'unknown'),
                'artist':       ', '.join(a['name'] for a in t.get('artists', [])),
                'duration_ms':  t.get('duration_ms', 0),
                'search_query': self._spotify_track_to_search_query(t),
            })
        return output

    async def download_spotify_track(self, url: str, user_id: int) -> dict:
        """
        Bitta Spotify track URL ni qabul qilib, YouTube orqali yuklab beradi.
        Qaytaradi: {"success": True, "filepath": ..., "title": ..., ...}
        """
        tracks = await self._spotify_get_tracks(url)
        if not tracks:
            return {"success": False, "error": "Spotify metadata olishda xato yoki track topilmadi"}

        track = tracks[0]
        search_query = f"ytsearch1:{track['search_query']}"
        logger.info(f"🎵 Spotify → YouTube qidirilmoqda: {track['search_query']}")

        result = await self._ytdlp_search_and_download(search_query, user_id, track['title'], track['artist'])
        if result.get("success"):
            result["platform"] = "spotify"
        return result

    async def download_spotify_playlist(self, url: str, user_id: int) -> list[dict]:
        """
        Spotify album yoki playlist URL — barcha tracklarni yuklab, natijalar ro'yxatini qaytaradi.
        Har element: {"success": bool, "filepath": ..., "title": ..., ...}
        """
        tracks = await self._spotify_get_tracks(url)
        if not tracks:
            return [{"success": False, "error": "Spotify playlist/album bo'sh yoki xato"}]

        results = []
        for track in tracks:
            search_query = f"ytsearch1:{track['search_query']}"
            logger.info(f"🎵 Spotify playlist → {track['search_query']}")
            result = await self._ytdlp_search_and_download(
                search_query, user_id, track['title'], track['artist']
            )
            if result.get("success"):
                result["platform"] = "spotify"
            results.append(result)

        return results

    async def _ytdlp_search_and_download(
        self, search_query: str, user_id: int, title: str = "audio", artist: str = ""
    ) -> dict:
        """yt-dlp ytsearch orqali qidiradi va MP3 yuklab beradi"""
        try:
            filename = f"{user_id}_{os.urandom(4).hex()}"
            filepath_template = os.path.join(self.download_path, f"{filename}.%(ext)s")

            ydl_opts = {
                'outtmpl':          filepath_template,
                'quiet':            True,
                'no_warnings':      True,
                'nocheckcertificate': True,
                'socket_timeout':   30,
                'retries':          3,
                'format':           'bestaudio/best',
                'postprocessors': [{
                    'key':             'FFmpegExtractAudio',
                    'preferredcodec':  'mp3',
                    'preferredquality': '192',
                }],
            }

            if PROXY_URL:
                ydl_opts['proxy'] = PROXY_URL

            loop = asyncio.get_running_loop()
            info = await loop.run_in_executor(
                None, lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(search_query, download=True)
            )

            if info and info.get('entries'):
                info = info['entries'][0]

            filepath = os.path.join(self.download_path, f"{filename}.mp3")
            if not os.path.exists(filepath):
                for f in os.listdir(self.download_path):
                    if f.startswith(filename):
                        filepath = os.path.join(self.download_path, f)
                        break

            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                return {
                    "success":  True,
                    "filepath": filepath,
                    "title":    title or (info.get('title', 'audio') if info else 'audio'),
                    "uploader": artist or (info.get('uploader', '') if info else ''),
                    "duration": (info.get('duration', 0) if info else 0),
                    "platform": "spotify",
                }

            return {"success": False, "error": "Fayl yaratilmadi"}

        except Exception as e:
            logger.error(f"_ytdlp_search_and_download xatosi: {str(e)[:120]}")
            return {"success": False, "error": str(e)[:100]}

    # ==================== 1. INVIDIOUS ====================
    async def download_with_invidious(self, url: str, user_id: int, is_video: bool = True) -> dict:
        video_id = self._extract_youtube_id(url)
        if not video_id:
            return {"success": False, "error": "YouTube video ID topilmadi"}

        INVIDIOUS_INSTANCES = [
            "https://inv.nadeko.net",
            "https://inv.tux.pizza",
            "https://invidious.privacydev.net",
            "https://invidious.fdn.fr",
            "https://invidious.io.lol",
            "https://y.com.sb",
            "https://invidious.lunar.icu",
            "https://invidious.tiekoetter.com",
            "https://invidious.projectsegfau.lt",
            "https://invidious.nerdvpn.de",
            "https://iv.datura.network",
            "https://yt.artemislena.eu",
        ]

        async with httpx.AsyncClient(timeout=15.0, verify=False, follow_redirects=True) as client:
            for instance in INVIDIOUS_INSTANCES:
                try:
                    resp = await client.get(
                        f"{instance}/api/v1/videos/{video_id}",
                        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                    )
                    if resp.status_code != 200:
                        logger.warning(f"⚠️ Invidious {instance}: {resp.status_code}")
                        continue

                    text = resp.text.strip()
                    if not text or not text.startswith('{'):
                        logger.warning(f"⚠️ Invidious {instance}: bo'sh javob")
                        continue

                    data = resp.json()
                    if data.get("error"):
                        logger.warning(f"⚠️ Invidious {instance}: {data.get('error')}")
                        continue

                    title  = data.get("title", "video")
                    dl_url = None

                    if is_video:
                        for fmt in data.get("formatStreams", []):
                            if fmt.get("type", "").startswith("video/mp4"):
                                if any(q in fmt.get("qualityLabel", "") for q in ["720p", "480p", "360p"]):
                                    dl_url = fmt.get("url")
                                    break
                        if not dl_url:
                            for fmt in data.get("formatStreams", []):
                                if fmt.get("type", "").startswith("video/mp4"):
                                    dl_url = fmt.get("url")
                                    break
                    else:
                        best_bitrate = 0
                        for fmt in data.get("adaptiveFormats", []):
                            if fmt.get("type", "").startswith("audio/"):
                                br = fmt.get("bitrate", 0)
                                if br > best_bitrate:
                                    best_bitrate = br
                                    dl_url = fmt.get("url")

                    if not dl_url:
                        logger.warning(f"⚠️ Invidious {instance}: URL topilmadi")
                        continue

                    filename = f"{user_id}_{os.urandom(4).hex()}"
                    ext      = "mp4" if is_video else "mp3"
                    filepath = os.path.join(self.download_path, f"{filename}.{ext}")

                    async with client.stream("GET", dl_url, timeout=120.0) as response:
                        if response.status_code != 200:
                            continue
                        with open(filepath, "wb") as f:
                            async for chunk in response.aiter_bytes(chunk_size=65536):
                                f.write(chunk)

                    size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
                    if size > 10_000:
                        logger.info(f"✅ Invidious success: {instance}")
                        return {
                            "success": True, "filepath": filepath, "title": title,
                            "uploader": data.get("author", ""), "duration": data.get("lengthSeconds", 0),
                            "platform": "youtube",
                        }
                    if os.path.exists(filepath):
                        os.remove(filepath)

                except Exception as e:
                    logger.warning(f"❌ Invidious {instance}: {str(e)[:80]}")

        return {"success": False, "error": "Invidious ishlamadi"}

    # ==================== 2. PIPED ====================
    async def download_with_piped(self, url: str, user_id: int, is_video: bool = True) -> dict:
        video_id = self._extract_youtube_id(url)
        if not video_id:
            return {"success": False, "error": "YouTube video ID topilmadi"}

        PIPED_INSTANCES = [
            "https://piped-api.garudalinux.org",
            "https://pipedapi.tokhmi.xyz",
            "https://pipedapi.moomoo.me",
            "https://pa.il.senny.xyz",
            "https://api.piped.projectsegfau.lt",
            "https://pipedapi.kavin.rocks",
        ]

        async with httpx.AsyncClient(timeout=15.0, verify=False, follow_redirects=True) as client:
            for instance in PIPED_INSTANCES:
                try:
                    resp = await client.get(
                        f"{instance}/streams/{video_id}",
                        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                    )
                    if resp.status_code != 200:
                        logger.warning(f"⚠️ Piped {instance}: {resp.status_code}")
                        continue

                    text = resp.text.strip()
                    if not text or not text.startswith('{'):
                        logger.warning(f"⚠️ Piped {instance}: bo'sh javob")
                        continue

                    data = resp.json()
                    if data.get("error"):
                        continue

                    title  = data.get("title", "video")
                    dl_url = None

                    if is_video:
                        for stream in data.get("videoStreams", []):
                            if not stream.get("videoOnly", True):
                                if "720p" in stream.get("quality", "") or "480p" in stream.get("quality", ""):
                                    dl_url = stream.get("url")
                                    break
                        if not dl_url:
                            for stream in data.get("videoStreams", []):
                                if not stream.get("videoOnly", True):
                                    dl_url = stream.get("url")
                                    break
                    else:
                        best_br = 0
                        for stream in data.get("audioStreams", []):
                            br = stream.get("bitrate", 0)
                            if br > best_br:
                                best_br = br
                                dl_url  = stream.get("url")

                    if not dl_url:
                        continue

                    filename = f"{user_id}_{os.urandom(4).hex()}"
                    ext      = "mp4" if is_video else "mp3"
                    filepath = os.path.join(self.download_path, f"{filename}.{ext}")

                    async with client.stream("GET", dl_url, timeout=120.0) as response:
                        if response.status_code != 200:
                            continue
                        with open(filepath, "wb") as f:
                            async for chunk in response.aiter_bytes(chunk_size=65536):
                                f.write(chunk)

                    size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
                    if size > 10_000:
                        logger.info(f"✅ Piped success: {instance}")
                        return {
                            "success": True, "filepath": filepath, "title": title,
                            "uploader": data.get("uploader", ""), "duration": data.get("duration", 0),
                            "platform": "youtube",
                        }
                    if os.path.exists(filepath):
                        os.remove(filepath)

                except Exception as e:
                    logger.warning(f"❌ Piped {instance}: {str(e)[:80]}")

        return {"success": False, "error": "Piped ishlamadi"}

    # ==================== 3. TO'G'RIDAN SCRAPING ====================
    async def download_with_scraping(self, url: str, user_id: int, is_video: bool = True) -> dict:
        video_id = self._extract_youtube_id(url)
        if not video_id:
            return {"success": False, "error": "Video ID topilmadi"}

        HEADERS = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }

        try:
            import json as _json
            yt_url = f"https://www.youtube.com/watch?v={video_id}"

            async with httpx.AsyncClient(timeout=20.0, headers=HEADERS, follow_redirects=True) as client:
                resp = await client.get(yt_url)
                if resp.status_code != 200:
                    return {"success": False, "error": f"YouTube sahifasi ochmadi: {resp.status_code}"}

                html  = resp.text
                match = re.search(r'ytInitialPlayerResponse\s*=\s*(\{.+?\});\s*(?:var|const|let|<)', html)
                if not match:
                    match = re.search(r'ytInitialPlayerResponse\s*=\s*(\{.+?\})', html)
                if not match:
                    return {"success": False, "error": "Player response topilmadi"}

                player_data = _json.loads(match.group(1))
                streaming   = player_data.get("streamingData", {})
                title       = player_data.get("videoDetails", {}).get("title", "video")
                author      = player_data.get("videoDetails", {}).get("author", "")
                duration    = int(player_data.get("videoDetails", {}).get("lengthSeconds", 0))
                dl_url      = None

                if not is_video:
                    formats      = streaming.get("adaptiveFormats", [])
                    best_bitrate = 0
                    for fmt in formats:
                        mime    = fmt.get("mimeType", "")
                        bitrate = fmt.get("bitrate", 0)
                        if "audio" in mime and bitrate > best_bitrate and fmt.get("url"):
                            best_bitrate = bitrate
                            dl_url       = fmt["url"]
                else:
                    formats = streaming.get("formats", [])
                    for fmt in formats:
                        if fmt.get("url") and fmt.get("height", 0) <= 720:
                            dl_url = fmt["url"]
                            break
                    if not dl_url and formats:
                        dl_url = formats[0].get("url")

                if not dl_url:
                    return {"success": False, "error": "Stream URL topilmadi"}

                filename = f"{user_id}_{os.urandom(4).hex()}"
                ext      = "mp4" if is_video else "mp3"
                filepath = os.path.join(self.download_path, f"{filename}.{ext}")

                logger.info("⬇️ Scraping orqali yuklanmoqda...")
                async with client.stream("GET", dl_url, timeout=120.0) as response:
                    if response.status_code != 200:
                        return {"success": False, "error": f"Yuklash xatosi: {response.status_code}"}
                    with open(filepath, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=65536):
                            f.write(chunk)

                size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
                if size > 10_000:
                    logger.info(f"✅ Scraping success! ({size // 1024}KB)")
                    return {
                        "success": True, "filepath": filepath,
                        "title": title, "uploader": author,
                        "duration": duration, "platform": "youtube",
                    }
                if os.path.exists(filepath):
                    os.remove(filepath)
                return {"success": False, "error": "Fayl juda kichik"}

        except Exception as e:
            logger.warning(f"❌ Scraping xato: {str(e)[:100]}")
            return {"success": False, "error": str(e)[:100]}

    # ==================== 4. YT-DLP ====================
    async def download_with_ytdlp(self, url: str, user_id: int, is_video: bool = True) -> dict:
        player_clients_list = [['android'], ['ios'], ['web'], ['tv']]
        for player_clients in player_clients_list:
            result = await self._ytdlp_attempt(url, user_id, is_video, player_clients)
            if result.get("success"):
                return result
            err = result.get("error", "")
            if "Sign in" not in err and "bot" not in err.lower() and "confirm" not in err.lower():
                return result
        return {"success": False, "error": "yt-dlp: YouTube bu serverdan yuklab bo'lmaydi"}

    async def _ytdlp_attempt(self, url: str, user_id: int, is_video: bool, player_clients: list) -> dict:
        try:
            filename          = f"{user_id}_{os.urandom(4).hex()}"
            filepath_template = os.path.join(self.download_path, f"{filename}.%(ext)s")

            extractor_args = {'youtube': {'player_client': player_clients}}
            if PO_TOKEN:
                extractor_args['youtube']['po_token'] = [f'web+{PO_TOKEN}']
                if VISITOR_DATA:
                    extractor_args['youtube']['visitor_data'] = [VISITOR_DATA]
                logger.info("🔑 po_token ishlatilmoqda")

            ydl_opts = {
                'outtmpl':                filepath_template,
                'quiet':                  True,
                'no_warnings':            True,
                'nocheckcertificate':     True,
                'geo_bypass':             True,
                'socket_timeout':         30,
                'retries':                3,
                'extractor_args':         extractor_args,
                'check_formats':          False,
                'allow_unplayable_formats': True,
            }

            if not is_video:
                ydl_opts['postprocessors'] = [{
                    'key':              'FFmpegExtractAudio',
                    'preferredcodec':   'mp3',
                    'preferredquality': '192',
                }]

            cookie_file = self._find_cookie_file(url)
            if cookie_file:
                ydl_opts['cookiefile'] = cookie_file
            if PROXY_URL:
                ydl_opts['proxy'] = PROXY_URL

            loop = asyncio.get_running_loop()
            info = await loop.run_in_executor(
                None, lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=True)
            )

            title    = info.get('title', 'video') if info else 'video'
            ext      = "mp3" if not is_video else "mp4"
            filepath = os.path.join(self.download_path, f"{filename}.{ext}")

            if not os.path.exists(filepath):
                for f in os.listdir(self.download_path):
                    if f.startswith(filename):
                        filepath = os.path.join(self.download_path, f)
                        break

            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                logger.info(f"✅ yt-dlp success (clients={player_clients})")
                return {
                    "success":  True, "filepath": filepath, "title": title,
                    "uploader": info.get('uploader', '') if info else '',
                    "duration": info.get('duration', 0) if info else 0,
                    "platform": info.get('extractor', 'unknown') if info else 'unknown',
                }

            return {"success": False, "error": "Fayl yaratilmadi"}

        except Exception as e:
            logger.error(f"yt-dlp ({player_clients}): {str(e)[:120]}")
            return {"success": False, "error": str(e)[:100]}

    # ==================== 5. BOSHQA PLATFORMALAR ====================
    async def download_non_youtube(self, url: str, user_id: int, is_video: bool = True) -> dict:
        try:
            filename = f"{user_id}_{os.urandom(4).hex()}"
            ydl_opts = {
                'outtmpl':            os.path.join(self.download_path, f"{filename}.%(ext)s"),
                'quiet':              True,
                'no_warnings':        True,
                'nocheckcertificate': True,
                'socket_timeout':     30,
                'retries':            3,
                'format':             'best[filesize<50M]/best' if is_video else 'bestaudio/best',
            }
            if not is_video:
                ydl_opts['postprocessors'] = [{
                    'key':              'FFmpegExtractAudio',
                    'preferredcodec':   'mp3',
                    'preferredquality': '192',
                }]

            cookie_file = self._find_cookie_file(url)
            if cookie_file:
                ydl_opts['cookiefile'] = cookie_file
            if PROXY_URL:
                ydl_opts['proxy'] = PROXY_URL

            loop = asyncio.get_running_loop()
            info = await loop.run_in_executor(
                None, lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=True)
            )
            title    = info.get('title', 'video') if info else 'video'
            ext      = "mp3" if not is_video else "mp4"
            filepath = os.path.join(self.download_path, f"{filename}.{ext}")

            if not os.path.exists(filepath):
                for f in os.listdir(self.download_path):
                    if f.startswith(filename):
                        filepath = os.path.join(self.download_path, f)
                        break

            if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                return {
                    "success":  True, "filepath": filepath, "title": title,
                    "uploader": info.get('uploader', '') if info else '',
                    "duration": info.get('duration', 0) if info else 0,
                    "platform": info.get('extractor', 'unknown') if info else 'unknown',
                }
            return {"success": False, "error": "Fayl yuklanmadi"}

        except Exception as e:
            return {"success": False, "error": str(e)[:100]}

    # ==================== ASOSIY METODLAR ====================

    async def download_video(self, url: str, user_id: int) -> dict:
        if self._is_spotify_url(url):
            return {"success": False, "error": "Spotify faqat audio qo'llab-quvvatlanadi. /audio buyrug'ini ishlating."}

        if self._is_youtube_url(url):
            logger.info("📺 YouTube video yuklanmoqda...")
            for method in [
                lambda: self.download_with_scraping(url, user_id, is_video=True),
                lambda: self.download_with_invidious(url, user_id, is_video=True),
                lambda: self.download_with_piped(url, user_id, is_video=True),
                lambda: self.download_with_ytdlp(url, user_id, is_video=True),
            ]:
                res = await method()
                if res.get("success"):
                    return res
            return {"success": False, "error": "❌ YouTube yuklab bo'lmadi. PO_TOKEN kerak — Railway Variables ga qo'shing."}

        return await self.download_non_youtube(url, user_id, is_video=True)

    async def download_audio(self, url: str, user_id: int) -> dict:
        # --- Spotify ---
        if self._is_spotify_url(url):
            url_type = self._spotify_url_type(url)
            if url_type == 'track':
                logger.info("🎵 Spotify track yuklanmoqda...")
                return await self.download_spotify_track(url, user_id)
            elif url_type in ('album', 'playlist'):
                logger.info(f"🎵 Spotify {url_type} yuklanmoqda...")
                results = await self.download_spotify_playlist(url, user_id)
                # Birinchi muvaffaqiyatli natijani qaytaramiz (bot tomonida loop qilish mumkin)
                for r in results:
                    if r.get("success"):
                        return r
                return {"success": False, "error": "Spotify playlist/album yuklab bo'lmadi"}
            else:
                return {"success": False, "error": "Noto'g'ri Spotify URL (track/album/playlist bo'lishi kerak)"}

        # --- YouTube ---
        if self._is_youtube_url(url):
            logger.info("🎵 YouTube audio yuklanmoqda...")
            for method in [
                lambda: self.download_with_scraping(url, user_id, is_video=False),
                lambda: self.download_with_invidious(url, user_id, is_video=False),
                lambda: self.download_with_piped(url, user_id, is_video=False),
                lambda: self.download_with_ytdlp(url, user_id, is_video=False),
            ]:
                res = await method()
                if res.get("success"):
                    return res
            return {"success": False, "error": "❌ YouTube yuklab bo'lmadi. PO_TOKEN kerak."}

        # --- Boshqa platformalar ---
        return await self.download_non_youtube(url, user_id, is_video=False)

    async def download_spotify_all(self, url: str, user_id: int) -> list[dict]:
        """
        Spotify playlist yoki album barcha tracklarini yuklash uchun.
        Bot tomonida har bir natijani aylanib chiqing va faylni yuboring.
        """
        return await self.download_spotify_playlist(url, user_id)

    # ==================== TOZALASH ====================

    def cleanup_file(self, filepath: str):
        try:
            if filepath and os.path.exists(filepath):
                os.remove(filepath)
        except Exception as e:
            logger.error(f"Cleanup error: {e}")

    def cleanup_user_files(self, user_id: int):
        try:
            for f in os.listdir(self.download_path):
                if f.startswith(str(user_id)):
                    self.cleanup_file(os.path.join(self.download_path, f))
        except Exception as e:
            logger.error(f"Cleanup user files error: {e}")
