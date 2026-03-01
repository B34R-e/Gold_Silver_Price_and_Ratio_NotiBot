"""
Config Manager — đọc config.json + .env
"""
import json
import os
from pathlib import Path
from dotenv import load_dotenv


class Config:
    """Quản lý cấu hình từ config.json và .env"""

    def __init__(self, config_path: str = "config.json", env_path: str = ".env"):
        # Load .env
        env_file = Path(env_path)
        if env_file.exists():
            load_dotenv(env_file)

        # Load config.json
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_file, "r", encoding="utf-8") as f:
            self._data = json.load(f)

        # Store config path for saving
        self._config_path = config_path

        # Parse delta config
        self.delta_gold = self._parse_delta(self._data.get("delta", {}).get("gold", "0.25%"))
        self.delta_silver = self._parse_delta(self._data.get("delta", {}).get("silver", "0.25%"))

        # Channels
        self.channels: list[str] = self._data.get("channels", ["telegram", "discord"])

        # Secrets from .env
        self.telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
        self.discord_webhook_url: str = os.getenv("DISCORD_WEBHOOK_URL", "")

    def save_to_file(self):
        """Ghi config hiện tại (delta) lại vào config.json"""
        # Chuyển delta ngược lại thành format config
        self._data["delta"]["gold"] = self._delta_to_config(self.delta_gold)
        self._data["delta"]["silver"] = self._delta_to_config(self.delta_silver)

        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=4, ensure_ascii=False)

    @staticmethod
    def _delta_to_config(delta: dict):
        """Chuyển delta dict ngược lại thành giá trị config"""
        if delta["type"] == "percent":
            return f"{delta['value'] * 100}%"
        else:
            return delta["value"]

    @staticmethod
    def _parse_delta(value) -> dict:
        """
        Parse delta value thành dict {'type': 'percent'|'absolute', 'value': float}

        Ví dụ:
            "0.25%" -> {'type': 'percent', 'value': 0.0025}
            50      -> {'type': 'absolute', 'value': 50.0}
            "50"    -> {'type': 'absolute', 'value': 50.0}
        """
        if isinstance(value, str) and value.endswith("%"):
            pct = float(value.rstrip("%"))
            return {"type": "percent", "value": pct / 100.0}
        else:
            return {"type": "absolute", "value": float(value)}

    def get_delta_threshold(self, symbol: str, current_price: float) -> float:
        """
        Tính ngưỡng biến động thực tế dựa trên config delta.

        Args:
            symbol: 'gold' hoặc 'silver'
            current_price: giá hiện tại (dùng nếu delta là %)

        Returns:
            Ngưỡng tuyệt đối (USD)
        """
        delta = self.delta_gold if symbol == "gold" else self.delta_silver

        if delta["type"] == "percent":
            return current_price * delta["value"]
        else:
            return delta["value"]
