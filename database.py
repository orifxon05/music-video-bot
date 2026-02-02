import psycopg2
from psycopg2.extras import RealDictCursor
import os
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
            
            # Admins (oddiy ro'yxat sifatida)
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

# Global obyekt
db = Database()
