"""Ma'lumotlar bazasi moduli — PostgreSQL va SQLite qo'llab-quvvatlash"""
import os
import sqlite3
import json
import logging

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

from config import DATABASE_URL, ADMIN_ID

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)


class Database:
    def __init__(self):
        self.database_url = DATABASE_URL
        self.sqlite_file = "local_database.db"
        self.use_sqlite = not (self.database_url and HAS_PSYCOPG2)

        if not self.use_sqlite:
            # PostgreSQL'ga ulanib ko'rish
            conn = self._pg_connect()
            if conn:
                try:
                    conn.close()
                    logger.info("✅ PostgreSQL ulandi")
                except:
                    pass
            else:
                logger.warning("⚠️ PostgreSQL ishlamadi — SQLite ga o'tilmoqda")
                self.use_sqlite = True

        if self.use_sqlite:
            logger.info("✅ SQLite ishlatilmoqda")

        self.create_tables()

    # ==================== ULANISH ====================

    def _pg_connect(self):
        """PostgreSQL ulanishi"""
        try:
            conn = psycopg2.connect(
                self.database_url,
                sslmode='require',
                connect_timeout=10,
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=5,
                gssencmode='disable'
            )
            return conn
        except Exception as e:
            logger.error(f"PostgreSQL ulanish xatosi: {e}")
            return None

    def _get_connection(self):
        """Yangi DB ulanishi olish"""
        if self.use_sqlite:
            conn = sqlite3.connect(self.sqlite_file, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")  # Yaxshiroq concurrent access
            return conn
        else:
            for _ in range(3):
                conn = self._pg_connect()
                if conn:
                    return conn
            # PostgreSQL ishlamasa SQLite'ga fallback
            logger.error("PostgreSQL 3 marta ulanmadi — SQLite ga o'tilmoqda")
            self.use_sqlite = True
            return self._get_connection()

    def _close(self, conn):
        try:
            if conn:
                conn.close()
        except:
            pass

    # ==================== JADVAL YARATISH ====================

    def _add_column_if_not_exists(self, conn, table: str, column: str, col_type: str):
        """SQLite uchun xavfsiz ustun qo'shish"""
        try:
            cur = conn.cursor()
            cur.execute(f"PRAGMA table_info({table})")
            existing_cols = [row[1] for row in cur.fetchall()]
            if column not in existing_cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                conn.commit()
        except Exception as e:
            logger.debug(f"_add_column_if_not_exists ({table}.{column}): {e}")

    def create_tables(self):
        logger.info("🛠 Jadvallarni tekshirish va yaratish...")
        conn = self._get_connection()
        try:
            if self.use_sqlite:
                self._create_tables_sqlite(conn)
            else:
                self._create_tables_pg(conn)
            logger.info("🚀 Jadvallar tayyor")
        except Exception as e:
            logger.error(f"create_tables xatosi: {e}")
        finally:
            self._close(conn)

    def _create_tables_sqlite(self, conn):
        """SQLite jadvallarini yaratish"""
        # Users
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                full_name TEXT,
                username TEXT,
                joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_admin INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        self._add_column_if_not_exists(conn, 'users', 'is_admin', 'INTEGER DEFAULT 0')

        # Channels
        conn.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                channel_id TEXT PRIMARY KEY,
                name TEXT,
                url TEXT
            )
        """)
        conn.commit()

        # User Session
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_session (
                user_id INTEGER PRIMARY KEY,
                url TEXT,
                title TEXT,
                artist TEXT,
                audio_path TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

        # Search Results
        conn.execute("""
            CREATE TABLE IF NOT EXISTS search_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                result_key TEXT NOT NULL,
                results_json TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

        # File Cache
        conn.execute("""
            CREATE TABLE IF NOT EXISTS file_cache (
                url_hash TEXT PRIMARY KEY,
                cache_type TEXT NOT NULL,
                file_id TEXT NOT NULL,
                title TEXT,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

        # Stats
        conn.execute("CREATE TABLE IF NOT EXISTS stats (id INTEGER PRIMARY KEY, total_downloads INTEGER DEFAULT 0)")
        conn.execute("INSERT OR IGNORE INTO stats (id, total_downloads) VALUES (1, 0)")
        conn.commit()

        # Admin
        conn.execute("INSERT OR IGNORE INTO users (id, is_admin) VALUES (?, 1)", (ADMIN_ID,))
        conn.commit()

    def _create_tables_pg(self, conn):
        """PostgreSQL jadvallarini yaratish"""
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                full_name TEXT,
                username TEXT,
                joined_date TIMESTAMP DEFAULT NOW(),
                is_admin BOOLEAN DEFAULT FALSE
            )
        """)
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                channel_id TEXT PRIMARY KEY,
                name TEXT,
                url TEXT
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_session (
                user_id BIGINT PRIMARY KEY,
                url TEXT, title TEXT, artist TEXT, audio_path TEXT,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS search_results (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                result_key TEXT NOT NULL,
                results_json TEXT,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS file_cache (
                url_hash TEXT PRIMARY KEY,
                cache_type TEXT NOT NULL,
                file_id TEXT NOT NULL,
                title TEXT,
                cached_at TIMESTAMP DEFAULT NOW()
            )
        """)

        cur.execute("CREATE TABLE IF NOT EXISTS stats (id INTEGER PRIMARY KEY, total_downloads INTEGER DEFAULT 0)")
        cur.execute("INSERT INTO stats (id, total_downloads) VALUES (1, 0) ON CONFLICT (id) DO NOTHING")
        cur.execute("INSERT INTO users (id, is_admin) VALUES (%s, TRUE) ON CONFLICT (id) DO UPDATE SET is_admin = TRUE",
                    (ADMIN_ID,))

        conn.commit()
        cur.close()

    # ==================== FOYDALANUVCHILAR ====================

    def add_user(self, user_id, full_name, username):
        """Foydalanuvchi qo'shish yoki yangilash"""
        conn = self._get_connection()
        try:
            if self.use_sqlite:
                conn.execute(
                    "INSERT OR REPLACE INTO users (id, full_name, username) VALUES (?, ?, ?)",
                    (user_id, full_name, username)
                )
            else:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO users (id, full_name, username)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        full_name = EXCLUDED.full_name,
                        username = EXCLUDED.username
                """, (user_id, full_name, username))
            conn.commit()
        except Exception as e:
            logger.error(f"add_user xatosi (id={user_id}): {e}")
        finally:
            self._close(conn)

    def get_users(self):
        """Barcha foydalanuvchilar ID larini qaytarish"""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT id FROM users")
            rows = cur.fetchall()
            return [row['id'] if self.use_sqlite else row[0] for row in rows]
        except Exception as e:
            logger.error(f"get_users xatosi: {e}")
            return []
        finally:
            self._close(conn)

    def get_stats(self):
        """Statistika olish"""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM users")
            row = cur.fetchone()
            total_users = row[0] if row else 0

            total_downloads = 0
            try:
                cur.execute("SELECT total_downloads FROM stats WHERE id = 1")
                row = cur.fetchone()
                total_downloads = row[0] if row else 0
            except:
                pass

            return {"total_users": total_users, "total_downloads": total_downloads}
        except Exception as e:
            logger.error(f"get_stats xatosi: {e}")
            return {"total_users": 0, "total_downloads": 0}
        finally:
            self._close(conn)

    def increment_downloads(self):
        conn = self._get_connection()
        try:
            conn.execute("UPDATE stats SET total_downloads = total_downloads + 1 WHERE id = 1")
            conn.commit()
        except Exception as e:
            logger.debug(f"increment_downloads: {e}")
        finally:
            self._close(conn)

    # ==================== KANALLAR ====================

    def add_channel(self, channel_id, name, url):
        conn = self._get_connection()
        try:
            if self.use_sqlite:
                conn.execute(
                    "INSERT OR REPLACE INTO channels (channel_id, name, url) VALUES (?, ?, ?)",
                    (str(channel_id), name, url)
                )
            else:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO channels (channel_id, name, url) VALUES (%s, %s, %s)
                    ON CONFLICT (channel_id) DO UPDATE SET name = EXCLUDED.name, url = EXCLUDED.url
                """, (str(channel_id), name, url))
            conn.commit()
        except Exception as e:
            logger.error(f"add_channel xatosi: {e}")
        finally:
            self._close(conn)

    def get_channels(self):
        """Kanallar ro'yxatini qaytarish"""
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT channel_id, name, url FROM channels")
            rows = cur.fetchall()
            result = []
            for row in rows:
                if self.use_sqlite:
                    d = dict(row)
                else:
                    d = {"channel_id": row[0], "name": row[1], "url": row[2]}
                d['id'] = d['channel_id']  # check_subscription uchun moslik
                result.append(d)
            logger.info(f"Kanallar topildi: {len(result)} ta")
            return result
        except Exception as e:
            logger.error(f"get_channels xatosi: {e}")
            return []
        finally:
            self._close(conn)

    def remove_channel(self, index_or_id):
        """Kanalani o'chirish (index yoki channel_id bilan)"""
        channels = self.get_channels()
        if isinstance(index_or_id, int) and 0 <= index_or_id < len(channels):
            real_id = channels[index_or_id]['channel_id']
        else:
            real_id = str(index_or_id)

        conn = self._get_connection()
        try:
            if self.use_sqlite:
                conn.execute("DELETE FROM channels WHERE channel_id = ?", (real_id,))
            else:
                cur = conn.cursor()
                cur.execute("DELETE FROM channels WHERE channel_id = %s", (real_id,))
            conn.commit()
        except Exception as e:
            logger.error(f"remove_channel xatosi: {e}")
        finally:
            self._close(conn)

    # ==================== SESSION ====================

    def save_user_session(self, user_id, data: dict):
        """Foydalanuvchi sessiyasini saqlash"""
        conn = self._get_connection()
        try:
            if self.use_sqlite:
                conn.execute("""
                    INSERT OR REPLACE INTO user_session
                        (user_id, url, title, artist, audio_path, updated_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    user_id,
                    data.get('url'),
                    data.get('title'),
                    data.get('artist'),
                    data.get('audio_path')
                ))
            else:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO user_session (user_id, url, title, artist, audio_path)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET
                        url       = COALESCE(EXCLUDED.url,        user_session.url),
                        title     = COALESCE(EXCLUDED.title,      user_session.title),
                        artist    = COALESCE(EXCLUDED.artist,     user_session.artist),
                        audio_path= COALESCE(EXCLUDED.audio_path, user_session.audio_path),
                        updated_at= NOW()
                """, (
                    user_id,
                    data.get('url'),
                    data.get('title'),
                    data.get('artist'),
                    data.get('audio_path')
                ))
            conn.commit()
        except Exception as e:
            logger.error(f"save_user_session xatosi (id={user_id}): {e}")
        finally:
            self._close(conn)

    def get_user_session(self, user_id):
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            if self.use_sqlite:
                cur.execute(
                    "SELECT url, title, artist, audio_path FROM user_session WHERE user_id = ?",
                    (user_id,)
                )
            else:
                cur.execute(
                    "SELECT url, title, artist, audio_path FROM user_session WHERE user_id = %s",
                    (user_id,)
                )
            row = cur.fetchone()
            if not row:
                return None
            if self.use_sqlite:
                return dict(row)
            return {"url": row[0], "title": row[1], "artist": row[2], "audio_path": row[3]}
        except Exception as e:
            logger.error(f"get_user_session xatosi: {e}")
            return None
        finally:
            self._close(conn)

    # ==================== QIDIRUV NATIJALARI ====================

    def save_search_results(self, result_key, results: list):
        key_str = str(result_key)
        try:
            user_id = int(key_str.split("_")[-1]) if "_" in key_str else int(key_str)
        except:
            user_id = 0

        conn = self._get_connection()
        try:
            results_json = json.dumps(results, ensure_ascii=False)
            if self.use_sqlite:
                conn.execute("DELETE FROM search_results WHERE result_key = ?", (key_str,))
                conn.execute(
                    "INSERT INTO search_results (user_id, result_key, results_json) VALUES (?, ?, ?)",
                    (user_id, key_str, results_json)
                )
            else:
                cur = conn.cursor()
                cur.execute("DELETE FROM search_results WHERE result_key = %s", (key_str,))
                cur.execute(
                    "INSERT INTO search_results (user_id, result_key, results_json) VALUES (%s, %s, %s)",
                    (user_id, key_str, results_json)
                )
            conn.commit()
        except Exception as e:
            logger.error(f"save_search_results xatosi: {e}")
        finally:
            self._close(conn)

    def get_search_results(self, result_key):
        conn = self._get_connection()
        try:
            key_str = str(result_key)
            cur = conn.cursor()
            if self.use_sqlite:
                cur.execute(
                    "SELECT results_json FROM search_results WHERE result_key = ? ORDER BY updated_at DESC LIMIT 1",
                    (key_str,)
                )
            else:
                cur.execute(
                    "SELECT results_json FROM search_results WHERE result_key = %s ORDER BY updated_at DESC LIMIT 1",
                    (key_str,)
                )
            row = cur.fetchone()
            if not row:
                return None
            return json.loads(row[0] if not self.use_sqlite else row['results_json'])
        except Exception as e:
            logger.error(f"get_search_results xatosi ({result_key}): {e}")
            return None
        finally:
            self._close(conn)

    # ==================== FAYL KESHI ====================

    def save_file_cache(self, url_hash, cache_type, file_id, title=""):
        conn = self._get_connection()
        try:
            if self.use_sqlite:
                conn.execute("""
                    INSERT OR REPLACE INTO file_cache
                        (url_hash, cache_type, file_id, title, cached_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (url_hash, cache_type, file_id, title))
            else:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO file_cache (url_hash, cache_type, file_id, title)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (url_hash) DO UPDATE SET
                        file_id   = EXCLUDED.file_id,
                        title     = EXCLUDED.title,
                        cached_at = NOW()
                """, (url_hash, cache_type, file_id, title))
            conn.commit()
        except Exception as e:
            logger.error(f"save_file_cache xatosi: {e}")
        finally:
            self._close(conn)

    def get_file_cache(self, url_hash, cache_type):
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            if self.use_sqlite:
                cur.execute(
                    "SELECT file_id FROM file_cache WHERE url_hash = ? AND cache_type = ?",
                    (url_hash, cache_type)
                )
            else:
                cur.execute(
                    "SELECT file_id FROM file_cache WHERE url_hash = %s AND cache_type = %s",
                    (url_hash, cache_type)
                )
            row = cur.fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.debug(f"get_file_cache: {e}")
            return None
        finally:
            self._close(conn)

    def get_cache_stats(self):
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT cache_type, COUNT(*) FROM file_cache GROUP BY cache_type")
            rows = cur.fetchall()
            stats = {"audio": 0, "video": 0}
            for row in rows:
                stats[row[0]] = row[1]
            return stats
        except Exception as e:
            logger.debug(f"get_cache_stats: {e}")
            return {"audio": 0, "video": 0}
        finally:
            self._close(conn)

    def clear_old_cache(self, days=30):
        """Eski kesh yozuvlarini o'chirish"""
        conn = self._get_connection()
        try:
            if self.use_sqlite:
                conn.execute(f"DELETE FROM file_cache WHERE cached_at < datetime('now', '-{days} days')")
                conn.execute("DELETE FROM search_results WHERE updated_at < datetime('now', '-7 days')")
                conn.execute("DELETE FROM user_session WHERE updated_at < datetime('now', '-1 days')")
            else:
                cur = conn.cursor()
                cur.execute(f"DELETE FROM file_cache WHERE cached_at < NOW() - INTERVAL '{days} days'")
                cur.execute("DELETE FROM search_results WHERE updated_at < NOW() - INTERVAL '7 days'")
                cur.execute("DELETE FROM user_session WHERE updated_at < NOW() - INTERVAL '1 day'")
            conn.commit()
            logger.info("🧹 Eski kesh o'chirildi")
        except Exception as e:
            logger.error(f"clear_old_cache xatosi: {e}")
        finally:
            self._close(conn)


db = Database()
