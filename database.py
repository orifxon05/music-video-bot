"""PostgreSQL Database moduli"""
import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL")
        if self.database_url:
            logger.info(f"DATABASE_URL topildi: {self.database_url[:30]}...")
        else:
            logger.warning("DATABASE_URL topilmadi!")
        self._init_db()

    def _get_connection(self):
        """Database ulanishini olish"""
        # Railway PostgreSQL uchun SSL
        return psycopg2.connect(
            self.database_url, 
            cursor_factory=RealDictCursor,
            sslmode='require'
        )

    def _init_db(self):
        """Jadvallarni yaratish"""
        if not self.database_url:
            print("DATABASE_URL topilmadi, lokal rejimda ishlamoqda")
            return
        
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # Users jadvali
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Channels jadvali
            cur.execute("""
                CREATE TABLE IF NOT EXISTS channels (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    channel_id VARCHAR(50) NOT NULL,
                    url VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Stats jadvali
            cur.execute("""
                CREATE TABLE IF NOT EXISTS stats (
                    id SERIAL PRIMARY KEY,
                    key VARCHAR(50) UNIQUE NOT NULL,
                    value INTEGER DEFAULT 0
                )
            """)
            
            # total_downloads boshlang'ich qiymat
            cur.execute("""
                INSERT INTO stats (key, value) VALUES ('total_downloads', 0)
                ON CONFLICT (key) DO NOTHING
            """)
            
            conn.commit()
            cur.close()
            conn.close()
            print("PostgreSQL database tayyor!")
        except Exception as e:
            print(f"Database init error: {e}")

    def add_user(self, user_id):
        """Foydalanuvchi qo'shish"""
        if not self.database_url:
            return False
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING",
                (user_id,)
            )
            conn.commit()
            cur.close()
            conn.close()
            return True
        except Exception as e:
            print(f"Add user error: {e}")
            return False

    def get_users(self):
        """Barcha foydalanuvchilar"""
        if not self.database_url:
            return []
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("SELECT user_id FROM users")
            users = [row['user_id'] for row in cur.fetchall()]
            cur.close()
            conn.close()
            return users
        except Exception as e:
            print(f"Get users error: {e}")
            return []

    def add_channel(self, name, channel_id, url):
        """Kanal qo'shish"""
        logger.info(f"Kanal qo'shilmoqda: {name}, {channel_id}, {url}")
        if not self.database_url:
            logger.error("DATABASE_URL yo'q!")
            return False
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO channels (name, channel_id, url) VALUES (%s, %s, %s)",
                (name, channel_id, url)
            )
            conn.commit()
            cur.close()
            conn.close()
            logger.info("Kanal muvaffaqiyatli qo'shildi!")
            return True
        except Exception as e:
            logger.error(f"Add channel error: {e}")
            return False

    def get_channels(self):
        """Barcha kanallar"""
        if not self.database_url:
            return []
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("SELECT name, channel_id as id, url FROM channels ORDER BY id")
            channels = [dict(row) for row in cur.fetchall()]
            cur.close()
            conn.close()
            return channels
        except Exception as e:
            print(f"Get channels error: {e}")
            return []

    def remove_channel(self, index):
        """Kanalni o'chirish (index bo'yicha)"""
        if not self.database_url:
            return False
        try:
            channels = self.get_channels()
            if 0 <= index < len(channels):
                channel = channels[index]
                conn = self._get_connection()
                cur = conn.cursor()
                cur.execute(
                    "DELETE FROM channels WHERE channel_id = %s AND name = %s",
                    (channel['id'], channel['name'])
                )
                conn.commit()
                cur.close()
                conn.close()
                return True
            return False
        except Exception as e:
            print(f"Remove channel error: {e}")
            return False

    def clear_channels(self):
        """Barcha kanallarni o'chirish"""
        if not self.database_url:
            return
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM channels")
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            print(f"Clear channels error: {e}")

    def increment_downloads(self):
        """Yuklanishlar sonini oshirish"""
        if not self.database_url:
            return
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute(
                "UPDATE stats SET value = value + 1 WHERE key = 'total_downloads'"
            )
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            print(f"Increment downloads error: {e}")

    def get_stats(self):
        """Statistikani olish"""
        if not self.database_url:
            return {"total_users": 0, "total_downloads": 0, "channels_count": 0}
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # Users count
            cur.execute("SELECT COUNT(*) as count FROM users")
            total_users = cur.fetchone()['count']
            
            # Downloads
            cur.execute("SELECT value FROM stats WHERE key = 'total_downloads'")
            row = cur.fetchone()
            total_downloads = row['value'] if row else 0
            
            # Channels count
            cur.execute("SELECT COUNT(*) as count FROM channels")
            channels_count = cur.fetchone()['count']
            
            cur.close()
            conn.close()
            
            return {
                "total_users": total_users,
                "total_downloads": total_downloads,
                "channels_count": channels_count
            }
        except Exception as e:
            print(f"Get stats error: {e}")
            return {"total_users": 0, "total_downloads": 0, "channels_count": 0}


db = Database()
