import json
import os

class Database:
    def __init__(self, db_file="db.json"):
        self.db_file = db_file
        self.data = self._load_data()
        self._load_env_channels()  # Environment'dan kanallarni yuklash

    def _load_env_channels(self):
        """Environment variable'dan kanallarni yuklash"""
        # CHANNELS format: "Kanal1|-1001234567890|https://t.me/kanal1,Kanal2|-1009876543210|https://t.me/kanal2"
        env_channels = os.getenv("CHANNELS", "")
        if env_channels and not self.data.get("channels"):
            channels = []
            for ch in env_channels.split(","):
                parts = ch.strip().split("|")
                if len(parts) == 3:
                    channels.append({
                        "name": parts[0].strip(),
                        "id": parts[1].strip(),
                        "url": parts[2].strip()
                    })
            if channels:
                self.data["channels"] = channels

    def _load_data(self):
        if os.path.exists(self.db_file):
            with open(self.db_file, "r") as f:
                return json.load(f)
        return {
            "users": [],
            "channels": [], # List of dicts: {"name": "", "id": "", "url": ""}
            "stats": {"total_downloads": 0}
        }

    def _save_data(self):
        with open(self.db_file, "w") as f:
            json.dump(self.data, f, indent=4)

    def add_user(self, user_id):
        if user_id not in self.data["users"]:
            self.data["users"].append(user_id)
            self._save_data()
            return True
        return False

    def get_users(self):
        return self.data["users"]

    def add_channel(self, name, channel_id, url):
        self.data["channels"].append({
            "name": name,
            "id": channel_id,
            "url": url
        })
        self._save_data()

    def get_channels(self):
        return self.data["channels"]

    def clear_channels(self):
        self.data["channels"] = []
        self._save_data()
    
    def remove_channel(self, index):
        if 0 <= index < len(self.data["channels"]):
            self.data["channels"].pop(index)
            self._save_data()
            return True
        return False

    def increment_downloads(self):
        self.data["stats"]["total_downloads"] += 1
        self._save_data()

    def get_stats(self):
        return {
            "total_users": len(self.data["users"]),
            "total_downloads": self.data.get("stats", {}).get("total_downloads", 0),
            "channels_count": len(self.data["channels"])
        }

db = Database()
