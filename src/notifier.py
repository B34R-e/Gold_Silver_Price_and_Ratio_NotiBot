"""
Notification Dispatcher + Channel Adapters (Telegram, Discord)
Sử dụng asyncio Queue để gửi tin nhắn non-blocking.
"""
import asyncio
import logging
import time
from abc import ABC, abstractmethod
from threading import Thread

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
            elif resp.status_code == 429:
                # Telegram rate limit — đợi rồi retry
                retry_after = resp.json().get("parameters", {}).get("retry_after", 5)
                logger.warning(f"Telegram rate limited, retrying after {retry_after}s")
                time.sleep(retry_after)
                return self.send(message)  # retry 1 lần
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
    """
    Điều phối gửi message đến các kênh đã cấu hình.
    Sử dụng background thread + queue để không block event loop.
    """

    def __init__(self, config: Config):
        self.config = config
        self._adapters: list[ChannelAdapter] = []
        self._init_adapters()

        # Message queue (thread-safe)
        from queue import Queue
        self._queue: Queue = Queue()
        self._worker_running = False
        self._worker_thread: Thread | None = None
        self._stats = {"sent": 0, "failed": 0, "queued": 0}

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

    def start_worker(self):
        """Khởi động background worker thread cho message queue"""
        self._worker_running = True
        self._worker_thread = Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()
        logger.info("Notification worker started (background thread)")

    def stop_worker(self):
        """Dừng worker thread"""
        self._worker_running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=5)
        logger.info(
            f"Notification worker stopped. "
            f"Stats: {self._stats['sent']} sent, {self._stats['failed']} failed, "
            f"{self._queue.qsize()} remaining in queue"
        )

    def _worker_loop(self):
        """Background loop: lấy message từ queue và gửi"""
        while self._worker_running or not self._queue.empty():
            try:
                # Đợi message tối đa 1 giây, nếu không có thì tiếp tục loop
                try:
                    message = self._queue.get(timeout=1)
                except Exception:
                    continue

                # Gửi đến tất cả adapters
                for adapter in self._adapters:
                    try:
                        success = adapter.send(message)
                        if success:
                            self._stats["sent"] += 1
                        else:
                            self._stats["failed"] += 1
                            # Retry 1 lần
                            logger.info(f"Retrying {adapter.name()}...")
                            if adapter.send(message):
                                self._stats["sent"] += 1
                            else:
                                self._stats["failed"] += 1
                    except Exception as e:
                        self._stats["failed"] += 1
                        logger.error(f"Failed to send via {adapter.name()}: {e}")

                self._queue.task_done()

            except Exception as e:
                logger.error(f"Worker error: {e}")

    def send_alert(self, alert: Alert):
        """Đẩy alert vào queue (instant, không block)"""
        message = alert.format_message()
        self._enqueue(message)

    def send_message(self, message: str):
        """Đẩy tin nhắn vào queue (instant, không block)"""
        self._enqueue(message)

    def send_message_sync(self, message: str):
        """Gửi tin nhắn đồng bộ (chỉ dùng cho startup/shutdown)"""
        for adapter in self._adapters:
            try:
                adapter.send(message)
            except Exception as e:
                logger.error(f"Failed to send via {adapter.name()}: {e}")

    def _enqueue(self, message: str):
        """Thêm message vào queue"""
        self._stats["queued"] += 1
        queue_size = self._queue.qsize()
        self._queue.put(message)
        if queue_size > 5:
            logger.warning(f"Message queue backing up: {queue_size + 1} pending")

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()

    @property
    def stats(self) -> dict:
        return self._stats.copy()
