import sqlite3
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
        self.use_sqlite = False
        self.sqlite_file = "local_database.db"
        
        if self.database_url:
            self.conn = self._get_connection()
            if self.conn:
                try:
                    self.create_tables()
                    if self.use_sqlite:
                        logger.info("✅ SQLite ulandi (Local Fallback)")
                    else:
                        logger.info("✅ PostgreSQL ulandi va tayyor")
                except Exception as e:
                    logger.error(f"Table creation error: {e}")
            else:
                logger.warning("⚠️ PostgreSQL-ga ulanib bo'lmadi! SQLite-ga o'tilmoqda...")
                self.use_sqlite = True
                self.create_tables()
                logger.info("✅ SQLite ulandi (Local Fallback)")
        else:
            logger.warning("❌ DATABASE_URL topilmadi! SQLite ishlatiladi")
            self.use_sqlite = True
            self.create_tables()

    def _get_connection(self, retries=3):
        if self.use_sqlite or not self.database_url:
            try:
                conn = sqlite3.connect(self.sqlite_file, check_same_thread=False)
                conn.row_factory = sqlite3.Row # Dictionary-like access
                return conn
            except Exception as e:
                logger.error(f"SQLite connection error: {e}")
                return None
        
        for i in range(retries):
            try:
                # SSL ulanishni yanada barqaror qilish uchun parametrlar
                conn = psycopg2.connect(
                    self.database_url, 
                    sslmode='require',
                    connect_timeout=10,
                    keepalives=1,
                    keepalives_idle=30,
                    keepalives_interval=10,
                    keepalives_count=5,
                    gssencmode='disable' # GSSAPI muammolarini oldini olish
                )
                return conn
            except Exception as e:
                logger.error(f"Connection attempt {i+1} failed: {e}")
                if i < retries - 1:
                    import time
                    time.sleep(2) # 2 soniya kutib ko'rish
                else:
                    logger.error("All PostgreSQL connection attempts failed. Switching to SQLite for this session.")
                    self.use_sqlite = True
                    return self._get_connection() # SQLite-ga qaytish
        return None

    def _transform_query(self, query):
        """PostgreSQL so'rovlarini SQLite-ga moslashtirish"""
        if self.use_sqlite:
            query = query.replace("ON CONFLICT (id) DO NOTHING", "OR IGNORE")
            query = query.replace("ON CONFLICT (id) DO UPDATE SET", "OR REPLACE")
            query = query.replace("EXCLUDED.", "")
            query = query.replace("%s", "?")
            # Ba'zi murakkab ON CONFLICT larni SQLite-da OR REPLACE bilan hal qilamiz
            if "ON CONFLICT" in query:
                parts = query.split("ON CONFLICT")
                query = parts[0].strip()
                if "INSERT" in query:
                    query = query.replace("INSERT", "INSERT OR REPLACE")
            
            # NOW() -> CURRENT_TIMESTAMP
            query = query.replace("NOW()", "CURRENT_TIMESTAMP")
            # INTERVAL 'X days' -> '-X days' (SQLite-da boshqacha)
            import re
            # PostgreSQL: cached_at < NOW() - INTERVAL '30 days'
            # SQLite: cached_at < datetime('now', '-30 days')
            query = re.sub(r"NOW\(\) - INTERVAL '(\d+) days'", r"datetime('now', '-\1 days')", query)
            query = re.sub(r"CURRENT_TIMESTAMP - INTERVAL '(\d+) days'", r"datetime('now', '-\1 days')", query)
            
        return query

    def _execute_safe(self, query, params=None):
        """Har bir so'rovni alohida commit bilan bajarish"""
        conn = self._get_connection()
        if not conn: return
        try:
            query = self._transform_query(query)
            cur = conn.cursor()
            cur.execute(query, params or ())
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
             # logger.debug(f"Safe execute error: {e}")
             if conn: conn.close()

    def create_tables(self):
        """Har bir jadvalni alohida yaratish va commit qilish"""
        logger.info("🛠 Jadvallarni tekshirish va yaratish...")
        
        # 1. Users
        self._execute_safe("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                full_name TEXT,
                username TEXT,
                joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_admin BOOLEAN DEFAULT FALSE
            )
        """)
        self._execute_safe("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE")

        # 2. Channels
        self._execute_safe("""
            CREATE TABLE IF NOT EXISTS channels (
                id SERIAL PRIMARY KEY,
                channel_id TEXT NOT NULL,
                name TEXT,
                url TEXT
            )
        """)

        # 3. User Session (ENG MUHIMI)
        self._execute_safe("""
            CREATE TABLE IF NOT EXISTS user_session (
                user_id BIGINT PRIMARY KEY,
                url TEXT,
                title TEXT,
                artist TEXT,
                audio_path TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 4. Search Results
        self._execute_safe("""
            CREATE TABLE IF NOT EXISTS search_results (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                result_key TEXT NOT NULL,
                results_json TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 5. File Cache
        self._execute_safe("""
            CREATE TABLE IF NOT EXISTS file_cache (
                url_hash TEXT PRIMARY KEY,
                cache_type TEXT NOT NULL,
                file_id TEXT NOT NULL,
                title TEXT,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 6. Stats - Bu jadval xato berayotgan bo'lsa ham boshqalarga xalaqit bermaydigan qildim
        self._execute_safe("CREATE TABLE IF NOT EXISTS stats (id INTEGER PRIMARY KEY, total_downloads INTEGER DEFAULT 0)")
        self._execute_safe("ALTER TABLE stats ADD COLUMN IF NOT EXISTS total_downloads INTEGER DEFAULT 0")
        
        # Stats jadvalidagi 'key' ustuni xatosini aylanib o'tish uchun try-except ishlatilgan _execute_safe ichida
        self._execute_safe("INSERT INTO stats (id, total_downloads) VALUES (1, 0) ON CONFLICT (id) DO NOTHING")
        
        # Adminni qo'shish
        self._execute_safe("INSERT INTO users (id, is_admin) VALUES (%s, TRUE) ON CONFLICT (id) DO UPDATE SET is_admin = TRUE", (ADMIN_ID,))
        
        logger.info("🚀 Baza jadvallari jarayoni yakunlandi")

    def add_user(self, user_id, full_name, username):
        self._execute_safe("""
            INSERT INTO users (id, full_name, username)
            VALUES (%s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
            full_name = EXCLUDED.full_name,
            username = EXCLUDED.username
        """, (user_id, full_name, username))

    def get_users(self):
        conn = self._get_connection()
        if not conn: return []
        try:
            if self.use_sqlite:
                cur = conn.cursor()
            else:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                
            query = self._transform_query("SELECT id FROM users")
            cur.execute(query)
            users = cur.fetchall()
            cur.close()
            conn.close()
            return [u['id'] for u in users]
        except Exception as e:
            logger.error(f"get_users error: {e}")
            return []

    def get_stats(self):
        conn = self._get_connection()
        if not conn: return {"total_users": 0, "total_downloads": 0}
        try:
            if self.use_sqlite:
                cur = conn.cursor()
            else:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                
            query_users = self._transform_query("SELECT COUNT(*) as total_users FROM users")
            cur.execute(query_users)
            res_users = cur.fetchone()
            total_users = res_users['total_users'] if res_users else 0
            
            # stats jadvali xato bo'lsa ham bot to'xtab qolmasligi uchun
            total_downloads = 0
            try:
                query_stats = self._transform_query("SELECT total_downloads FROM stats WHERE id = 1")
                cur.execute(query_stats)
                row = cur.fetchone()
                total_downloads = row['total_downloads'] if row else 0
            except: pass
            
            cur.close()
            conn.close()
            return {"total_users": total_users, "total_downloads": total_downloads}
        except Exception as e:
            logger.error(f"get_stats error: {e}")
            return {"total_users": 0, "total_downloads": 0}

    def increment_downloads(self):
        self._execute_safe("UPDATE stats SET total_downloads = total_downloads + 1 WHERE id = 1")

    def add_channel(self, channel_id, name, url):
        self._execute_safe("INSERT INTO channels (channel_id, name, url) VALUES (%s, %s, %s)", (channel_id, name, url))

    def get_channels(self):
        conn = self._get_connection()
        if not conn: return []
        try:
            if self.use_sqlite:
                cur = conn.cursor()
            else:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                
            query = self._transform_query("SELECT channel_id, name, url FROM channels")
            cur.execute(query)
            res = cur.fetchall()
            # SQLite Row'larni lug'atga o'tkazish
            if self.use_sqlite:
                res = [dict(row) for row in res]
            cur.close()
            conn.close()
            return res
        except Exception as e:
            logger.error(f"get_channels error: {e}")
            return []

    def remove_channel(self, channel_id):
        self._execute_safe("DELETE FROM channels WHERE channel_id = %s", (channel_id,))

    def save_user_session(self, user_id, data):
        self._execute_safe("""
            INSERT INTO user_session (user_id, url, title, artist, audio_path)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
            url = COALESCE(EXCLUDED.url, user_session.url),
            title = COALESCE(EXCLUDED.title, user_session.title),
            artist = COALESCE(EXCLUDED.artist, user_session.artist),
            audio_path = COALESCE(EXCLUDED.audio_path, user_session.audio_path),
            updated_at = CURRENT_TIMESTAMP
        """, (user_id, data.get('url'), data.get('title'), data.get('artist'), data.get('audio_path')))

    def get_user_session(self, user_id):
        conn = self._get_connection()
        if not conn: return None
        try:
            if self.use_sqlite:
                cur = conn.cursor()
            else:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                
            query = self._transform_query("SELECT url, title, artist, audio_path FROM user_session WHERE user_id = %s")
            cur.execute(query, (user_id,))
            row = cur.fetchone()
            cur.close()
            conn.close()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"get_user_session error: {e}")
            return None

    def save_search_results(self, result_key, results):
        key_str = str(result_key)
        user_id = 0
        if "_" in key_str:
            try: user_id = int(key_str.split("_")[-1])
            except: pass
        else:
            try: user_id = int(key_str)
            except: pass
        self._execute_safe("INSERT INTO search_results (user_id, result_key, results_json) VALUES (%s, %s, %s)",
                         (user_id, key_str, json.dumps(results)))

    def get_search_results(self, result_key):
        """Saqlangan qidiruv natijalarini olish"""
        conn = self._get_connection()
        if not conn: return None
        try:
            key_str = str(result_key) # Stringga o'tkazamiz
            if self.use_sqlite:
                cur = conn.cursor()
            else:
                cur = conn.cursor(cursor_factory=RealDictCursor)
                
            query = self._transform_query("SELECT results_json FROM search_results WHERE result_key = %s ORDER BY updated_at DESC LIMIT 1")
            cur.execute(query, (key_str,))
            row = cur.fetchone()
            cur.close()
            conn.close()
            return json.loads(row['results_json']) if row else None
        except Exception as e:
            logger.error(f"get_search_results error for {result_key}: {e}")
            return None

    def save_file_cache(self, url_hash, cache_type, file_id, title=""):
        self._execute_safe("""
            INSERT INTO file_cache (url_hash, cache_type, file_id, title)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (url_hash) DO UPDATE SET
            file_id = EXCLUDED.file_id,
            title = EXCLUDED.title,
            cached_at = CURRENT_TIMESTAMP
        """, (url_hash, cache_type, file_id, title))

    def get_file_cache(self, url_hash, cache_type):
        conn = self._get_connection()
        if not conn: return None
        try:
            cur = conn.cursor()
            query = self._transform_query("SELECT file_id FROM file_cache WHERE url_hash = %s AND cache_type = %s")
            cur.execute(query, (url_hash, cache_type))
            row = cur.fetchone()
            cur.close()
            conn.close()
            return row[0] if row else None
        except: return None

    def get_cache_stats(self):
        conn = self._get_connection()
        if not conn: return {"audio": 0, "video": 0}
        try:
            cur = conn.cursor()
            query = self._transform_query("SELECT cache_type, COUNT(*) FROM file_cache GROUP BY cache_type")
            cur.execute(query)
            rows = cur.fetchall()
            stats = {"audio": 0, "video": 0}
            for row in rows: stats[row[0]] = row[1]
            cur.close()
            conn.close()
            return stats
        except: return {"audio": 0, "video": 0}

    def clear_old_cache(self, days=30):
        self._execute_safe(f"DELETE FROM file_cache WHERE cached_at < NOW() - INTERVAL '{days} days'")
        self._execute_safe("DELETE FROM search_results WHERE updated_at < NOW() - INTERVAL '7 days'")
        self._execute_safe("DELETE FROM user_session WHERE updated_at < NOW() - INTERVAL '1 day'")

db = Database()
