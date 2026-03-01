"""
Telegram Command Listener — nhận và xử lý commands từ Telegram group
Supports: /status, /delta, /help
"""
import logging
import time
from typing import Optional, Callable

import requests

logger = logging.getLogger(__name__)


class TelegramCommandListener:
    """
    Polling Telegram getUpdates API để nhận commands.
    Chạy trong background thread riêng.
    """

    API_URL = "https://api.telegram.org/bot{token}"

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._base_url = self.API_URL.format(token=bot_token)
        self._offset: int = 0
        self._running = False

        # Command handlers
        self._handlers: dict[str, Callable] = {}

    def register(self, command: str, handler: Callable):
        """Đăng ký handler cho command (ví dụ: '/status')"""
        self._handlers[command] = handler

    def poll_once(self) -> list[dict]:
        """
        Gọi getUpdates 1 lần, trả về danh sách messages mới.
        Non-blocking, timeout ngắn.
        """
        try:
            url = f"{self._base_url}/getUpdates"
            params = {"offset": self._offset, "timeout": 2, "allowed_updates": ["message"]}
            resp = requests.get(url, params=params, timeout=10)

            if resp.status_code != 200:
                logger.warning(f"Telegram getUpdates error: {resp.status_code}")
                return []

            data = resp.json()
            if not data.get("ok"):
                return []

            results = data.get("result", [])
            if results:
                # Cập nhật offset để không nhận lại message cũ
                self._offset = results[-1]["update_id"] + 1

            return results

        except requests.RequestException as e:
            logger.warning(f"Telegram poll error: {e}")
            return []

    def process_updates(self, updates: list[dict]):
        """Xử lý các updates, gọi handler phù hợp"""
        for update in updates:
            msg = update.get("message", {})
            text = msg.get("text", "").strip()
            chat = msg.get("chat", {})
            chat_id = str(chat.get("id", ""))

            # Chỉ xử lý tin từ chat đã cấu hình
            if chat_id != self.chat_id:
                continue

            if not text.startswith("/"):
                continue

            # Parse command và args
            parts = text.split()
            command = parts[0].split("@")[0].lower()  # Loại bỏ @botname
            args = parts[1:]

            logger.info(f"Command received: {command} {args}")

            handler = self._handlers.get(command)
            if handler:
                try:
                    handler(args)
                except Exception as e:
                    logger.error(f"Error handling command {command}: {e}")
            else:
                logger.debug(f"Unknown command: {command}")

    def reply(self, text: str):
        """Gửi tin nhắn trả lời vào chat"""
        url = f"{self._base_url}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": text}
        try:
            requests.post(url, json=payload, timeout=10)
        except requests.RequestException as e:
            logger.error(f"Telegram reply error: {e}")
