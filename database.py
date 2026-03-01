import psycopg2
from psycopg2.extras import RealDictCursor
import os
import json
import logging
from config import DATABASE_URL, ADMIN_ID

# Loggingni sozlash
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.database_url = DATABASE_URL
        try:
            # SSL rejimini yoqish (Render uchun shart)
            if self.database_url:
                self.conn = psycopg2.connect(self.database_url, sslmode='require')
                self.create_tables()
                logger.info("✅ Database ulandi")
            else:
                logger.error("❌ DATABASE_URL topilmadi!")
                self.conn = None
        except Exception as e:
            logger.error(f"Database init error: {e}")
            self.conn = None

    def _get_connection(self):
        """Yangi ulanish yaratish (Thread safety uchun)"""
        if not self.database_url:
            return None
        try:
            return psycopg2.connect(self.database_url, sslmode='require')
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return None

    def create_tables(self):
        """Jadvallarni yaratish"""
        if not self.conn: return
        try:
            cur = self.conn.cursor()
            
            # Users jadvali
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id BIGINT PRIMARY KEY,
                    full_name TEXT,
                    username TEXT,
                    joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_admin BOOLEAN DEFAULT FALSE
                )
            """)
            
            # Channels jadvali - Majburiy obuna uchun
            cur.execute("""
                CREATE TABLE IF NOT EXISTS channels (
                    id SERIAL PRIMARY KEY,
                    channel_id TEXT NOT NULL,
                    name TEXT,
                    url TEXT
                )
            """)
            
            # User session jadvali - user_music_data o'rniga (RAM dan bazaga)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_session (
                    user_id BIGINT PRIMARY KEY,
                    url TEXT,
                    title TEXT,
                    artist TEXT,
                    audio_path TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Search results jadvali - user_search_data o'rniga
            cur.execute("""
                CREATE TABLE IF NOT EXISTS search_results (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    result_key TEXT NOT NULL,
                    results_json TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # File cache jadvali - cache.json o'rniga
            cur.execute("""
                CREATE TABLE IF NOT EXISTS file_cache (
                    url_hash TEXT PRIMARY KEY,
                    cache_type TEXT NOT NULL,
                    file_id TEXT NOT NULL,
                    title TEXT,
                    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Downloads statistika jadvali
            cur.execute("""
                CREATE TABLE IF NOT EXISTS stats (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    total_downloads INTEGER DEFAULT 0
                )
            """)
            # Ustun borligini tekshirish (fallback)
            try:
                cur.execute("ALTER TABLE stats ADD COLUMN IF NOT EXISTS total_downloads INTEGER DEFAULT 0")
            except:
                pass
            
            cur.execute("INSERT INTO stats (id, total_downloads) VALUES (1, 0) ON CONFLICT (id) DO NOTHING")
            
            # Dastlabki adminni qo'shish
            cur.execute("INSERT INTO users (id, is_admin) VALUES (%s, TRUE) ON CONFLICT (id) DO UPDATE SET is_admin = TRUE", (ADMIN_ID,))
            
            self.conn.commit()
            cur.close()
        except Exception as e:
            logger.error(f"Create tables error: {e}")

    def add_user(self, user_id, full_name, username):
        """Foydalanuvchi qo'shish"""
        conn = self._get_connection()
        if not conn: return False
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO users (id, full_name, username)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE 
                SET full_name = EXCLUDED.full_name, 
                    username = EXCLUDED.username
            """, (user_id, full_name, username))
            conn.commit()
            cur.close()
            conn.close()
            return True
        except Exception as e:
            # logger.error(f"Add user error: {e}") 
            return False

    def get_users_count(self):
        """Foydalanuvchilar sonini olish"""
        conn = self._get_connection()
        if not conn: return 0
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM users")
            count = cur.fetchone()[0]
            conn.close()
            return count
        except Exception as e:
            logger.error(f"Get users count error: {e}")
            return 0

    def get_all_users(self):
        """Barcha foydalanuvchilarni olish (Broadcast uchun)"""
        conn = self._get_connection()
        if not conn: return []
        try:
            cur = conn.cursor()
            cur.execute("SELECT id FROM users")
            users = [row[0] for row in cur.fetchall()]
            conn.close()
            return users
        except Exception as e:
            logger.error(f"Get all users error: {e}")
            return []

    def add_channel(self, channel_id, name, url):
        """Kanal qo'shish"""
        conn = self._get_connection()
        if not conn: return False
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO channels (channel_id, name, url) VALUES (%s, %s, %s)", (channel_id, name, url))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Add channel error: {e}")
            return False

    def get_channels(self):
        """Kanallar ro'yxatini olish"""
        conn = self._get_connection()
        if not conn: return []
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            # channel_id ni 'id' deb qaytaramiz (kodimiz shuni kutadi)
            cur.execute("SELECT name, channel_id as id, url FROM channels ORDER BY id")
            channels = [dict(row) for row in cur.fetchall()]
            conn.close()
            return channels
        except Exception as e:
            logger.error(f"Get channels error: {e}")
            return []

    def remove_channel(self, channel_id):
        """Kanalni o'chirish"""
        conn = self._get_connection()
        if not conn: return False
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM channels WHERE channel_id = %s", (str(channel_id),))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Remove channel error: {e}")
            return False

    # ==================== USER SESSION (user_music_data o'rniga) ====================
    
    def save_user_session(self, user_id, data):
        """Foydalanuvchi sessiyasini saqlash (title, artist, url, audio_path)"""
        conn = self._get_connection()
        if not conn: return False
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO user_session (user_id, url, title, artist, audio_path, updated_at)
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id) DO UPDATE SET
                    url = COALESCE(EXCLUDED.url, user_session.url),
                    title = COALESCE(EXCLUDED.title, user_session.title),
                    artist = COALESCE(EXCLUDED.artist, user_session.artist),
                    audio_path = COALESCE(EXCLUDED.audio_path, user_session.audio_path),
                    updated_at = CURRENT_TIMESTAMP
            """, (
                user_id,
                data.get("url"),
                data.get("title"),
                data.get("artist"),
                data.get("audio_path")
            ))
            conn.commit()
            cur.close()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Save session error: {e}")
            return False
    
    def get_user_session(self, user_id):
        """Foydalanuvchi sessiyasini olish"""
        conn = self._get_connection()
        if not conn: return None
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("SELECT url, title, artist, audio_path FROM user_session WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            cur.close()
            conn.close()
            if row:
                return dict(row)
            return None
        except Exception as e:
            logger.error(f"Get session error: {e}")
            return None

    # ==================== SEARCH RESULTS (user_search_data o'rniga) ====================
    
    def save_search_results(self, key, results):
        """Qidiruv natijalarini saqlash (key = user_id yoki 'remix_user_id')"""
        conn = self._get_connection()
        if not conn: return False
        try:
            cur = conn.cursor()
            results_json = json.dumps(results, ensure_ascii=False)
            cur.execute("""
                INSERT INTO search_results (user_id, result_key, results_json, updated_at)
                VALUES (0, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT ON CONSTRAINT search_results_key_unique
                DO UPDATE SET results_json = EXCLUDED.results_json, updated_at = CURRENT_TIMESTAMP
            """, (str(key), results_json))
            conn.commit()
            cur.close()
            conn.close()
            return True
        except Exception as e:
            # Agar constraint mavjud bo'lmasa, oddiy delete + insert
            try:
                cur = conn.cursor()
                cur.execute("DELETE FROM search_results WHERE result_key = %s", (str(key),))
                cur.execute("""
                    INSERT INTO search_results (user_id, result_key, results_json, updated_at)
                    VALUES (0, %s, %s, CURRENT_TIMESTAMP)
                """, (str(key), json.dumps(results, ensure_ascii=False)))
                conn.commit()
                cur.close()
                conn.close()
                return True
            except Exception as e2:
                logger.error(f"Save search error: {e2}")
                return False
    
    def get_search_results(self, key):
        """Qidiruv natijalarini olish"""
        conn = self._get_connection()
        if not conn: return None
        try:
            cur = conn.cursor()
            cur.execute("SELECT results_json FROM search_results WHERE result_key = %s", (str(key),))
            row = cur.fetchone()
            cur.close()
            conn.close()
            if row and row[0]:
                return json.loads(row[0])
            return None
        except Exception as e:
            logger.error(f"Get search error: {e}")
            return None

    # ==================== FILE CACHE (cache.json o'rniga) ====================
    
    def save_file_cache(self, url_hash, cache_type, file_id, title=""):
        """Telegram file_id ni bazaga saqlash"""
        conn = self._get_connection()
        if not conn: return False
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO file_cache (url_hash, cache_type, file_id, title, cached_at)
                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (url_hash) DO UPDATE SET
                    file_id = EXCLUDED.file_id,
                    title = EXCLUDED.title,
                    cached_at = CURRENT_TIMESTAMP
            """, (url_hash, cache_type, file_id, title))
            conn.commit()
            cur.close()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Save cache error: {e}")
            return False
    
    def get_file_cache(self, url_hash, cache_type):
        """Telegram file_id ni bazadan olish"""
        conn = self._get_connection()
        if not conn: return None
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT file_id FROM file_cache 
                WHERE url_hash = %s AND cache_type = %s 
                AND cached_at > CURRENT_TIMESTAMP - INTERVAL '7 days'
            """, (url_hash, cache_type))
            row = cur.fetchone()
            cur.close()
            conn.close()
            if row:
                return row[0]
            return None
        except Exception as e:
            logger.error(f"Get cache error: {e}")
            return None
    
    def clear_old_cache(self):
        """7 kundan eski keshlarni tozalash"""
        conn = self._get_connection()
        if not conn: return
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM file_cache WHERE cached_at < CURRENT_TIMESTAMP - INTERVAL '7 days'")
            cur.execute("DELETE FROM search_results WHERE updated_at < CURRENT_TIMESTAMP - INTERVAL '1 day'")
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            logger.error(f"Clear cache error: {e}")

    # ==================== STATS ====================
    
    def get_stats(self):
        """Statistika olish"""
        conn = self._get_connection()
        if not conn: return {"total_users": 0, "total_downloads": 0}
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM users")
            total_users = cur.fetchone()[0]
            cur.execute("SELECT total_downloads FROM stats WHERE id = 1")
            row = cur.fetchone()
            total_downloads = row[0] if row else 0
            cur.close()
            conn.close()
            return {"total_users": total_users, "total_downloads": total_downloads}
        except Exception as e:
            logger.error(f"Get stats error: {e}")
            return {"total_users": 0, "total_downloads": 0}
    
    def increment_downloads(self):
        """Yuklanishlar sonini oshirish"""
        conn = self._get_connection()
        if not conn: return
        try:
            cur = conn.cursor()
            cur.execute("UPDATE stats SET total_downloads = total_downloads + 1 WHERE id = 1")
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            logger.error(f"Increment downloads error: {e}")
    
    def get_users(self):
        """Barcha foydalanuvchilar ID larini olish (Broadcast uchun)"""
        return self.get_all_users()

    def get_cache_stats(self):
        """Kesh statistikasini olish"""
        conn = self._get_connection()
        if not conn: return {"audio": 0, "video": 0}
        try:
            cur = conn.cursor()
            cur.execute("SELECT cache_type, COUNT(*) FROM file_cache GROUP BY cache_type")
            rows = cur.fetchall()
            cur.close()
            conn.close()
            result = {"audio": 0, "video": 0}
            for row in rows:
                result[row[0]] = row[1]
            return result
        except Exception as e:
            logger.error(f"Get cache stats error: {e}")
            return {"audio": 0, "video": 0}

# Global obyekt
db = Database()
