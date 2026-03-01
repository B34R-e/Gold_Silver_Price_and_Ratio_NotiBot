"""
Notification Dispatcher + Channel Adapters (Telegram, Discord)
"""
import logging
from abc import ABC, abstractmethod

import requests

from src.config import Config
from src.models import Alert

logger = logging.getLogger(__name__)


class ChannelAdapter(ABC):
    """Interface chung cho tất cả kênh thông báo"""

    @abstractmethod
    def send(self, message: str) -> bool:
        """Gửi tin nhắn. Return True nếu thành công."""
        pass

    @abstractmethod
    def name(self) -> str:
        pass


class TelegramAdapter(ChannelAdapter):
    """Gửi tin nhắn qua Telegram Bot API"""

    API_URL = "https://api.telegram.org/bot{token}/sendMessage"

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def name(self) -> str:
        return "Telegram"

    def send(self, message: str) -> bool:
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram: bot_token or chat_id not configured, skipping")
            return False

        url = self.API_URL.format(token=self.bot_token)
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML",
        }

        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info("Telegram: message sent successfully")
                return True
            else:
                logger.error(f"Telegram error {resp.status_code}: {resp.text}")
                return False
        except requests.RequestException as e:
            logger.error(f"Telegram request failed: {e}")
            return False


class DiscordAdapter(ChannelAdapter):
    """Gửi tin nhắn qua Discord Webhook"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def name(self) -> str:
        return "Discord"

    def send(self, message: str) -> bool:
        if not self.webhook_url:
            logger.warning("Discord: webhook_url not configured, skipping")
            return False

        payload = {"content": message}

        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=10)
            if resp.status_code in (200, 204):
                logger.info("Discord: message sent successfully")
                return True
            else:
                logger.error(f"Discord error {resp.status_code}: {resp.text}")
                return False
        except requests.RequestException as e:
            logger.error(f"Discord request failed: {e}")
            return False


class NotificationDispatcher:
    """Điều phối gửi message đến các kênh đã cấu hình"""

    def __init__(self, config: Config):
        self.config = config
        self._adapters: list[ChannelAdapter] = []
        self._init_adapters()

    def _init_adapters(self):
        """Khởi tạo adapters dựa trên config"""
        if "telegram" in self.config.channels:
            adapter = TelegramAdapter(
                bot_token=self.config.telegram_bot_token,
                chat_id=self.config.telegram_chat_id,
            )
            self._adapters.append(adapter)
            logger.info("Telegram adapter initialized")

        if "discord" in self.config.channels:
            adapter = DiscordAdapter(
                webhook_url=self.config.discord_webhook_url,
            )
            self._adapters.append(adapter)
            logger.info("Discord adapter initialized")

    def send_alert(self, alert: Alert):
        """Gửi alert đến tất cả kênh đã cấu hình"""
        message = alert.format_message()
        logger.info(f"Sending alert to {len(self._adapters)} channel(s)...")

        for adapter in self._adapters:
            try:
                success = adapter.send(message)
                if not success:
                    # Retry 1 lần
                    logger.info(f"Retrying {adapter.name()}...")
                    adapter.send(message)
            except Exception as e:
                logger.error(f"Failed to send via {adapter.name()}: {e}")

    def send_message(self, message: str):
        """Gửi tin nhắn tùy ý (dùng cho startup, error alerts...)"""
        for adapter in self._adapters:
            try:
                adapter.send(message)
            except Exception as e:
                logger.error(f"Failed to send via {adapter.name()}: {e}")
