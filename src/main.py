"""
Gold/Silver Price & Ratio NotiBot — Main Entry Point

Bot nhận giá XAUUSDT + XAGUSDT realtime qua Binance Futures WebSocket,
tính Gold/Silver Ratio, gửi thông báo qua Telegram + Discord khi giá biến động ≥ X.
"""
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

from src.config import Config
from src.models import PriceData
from src.price_fetcher import PriceFetcher
from src.alert_engine import AlertEngine
from src.notifier import NotificationDispatcher
from src.telegram_commands import TelegramCommandListener

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("notibot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("NotiBot")


class NotiBot:
    """Main bot class — wire mọi thứ lại"""

    def __init__(self, config_path: str = "config.json", env_path: str = ".env"):
        logger.info("=" * 50)
        logger.info("Gold/Silver NotiBot starting...")
        logger.info("=" * 50)

        # Load config
        self.config = Config(config_path=config_path, env_path=env_path)
        logger.info(f"Delta Gold: {self.config.delta_gold}")
        logger.info(f"Delta Silver: {self.config.delta_silver}")
        logger.info(f"Channels: {self.config.channels}")

        # Init modules
        self.alert_engine = AlertEngine(self.config)
        self.dispatcher = NotificationDispatcher(self.config)
        self.price_fetcher = PriceFetcher(on_price_update=self._on_price_update)

        # Telegram command listener
        self.cmd_listener = TelegramCommandListener(
            bot_token=self.config.telegram_bot_token,
            chat_id=self.config.telegram_chat_id,
        )
        self._register_commands()

        # State
        self._price_count = 0
        self._startup_sent = False
        self._latest_price: PriceData | None = None

    def _register_commands(self):
        """Đăng ký các Telegram commands"""
        self.cmd_listener.register("/status", self._cmd_status)
        self.cmd_listener.register("/delta", self._cmd_delta)
        self.cmd_listener.register("/help", self._cmd_help)
        logger.info("Telegram commands registered: /status, /delta, /help")

    # ── Command handlers ────────────────────────────────

    def _cmd_status(self, args: list[str]):
        """Xem giá hiện tại + config"""
        if self._latest_price is None:
            self.cmd_listener.reply("⏳ Chưa nhận được giá. Đợi vài giây...")
            return

        p = self._latest_price
        gold_delta = self._format_delta(self.config.delta_gold)
        silver_delta = self._format_delta(self.config.delta_silver)

        self.cmd_listener.reply(
            f"📊 Trạng thái NotiBot\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🥇 Vàng (XAU): ${p.gold:,.2f}\n"
            f"🥈 Bạc (XAG): ${p.silver:,.4f}\n"
            f"⚖️ Ratio: {p.ratio}\n"
            f"🕐 {p.timestamp.strftime('%H:%M:%S %d/%m/%Y')}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚙️ Delta Vàng: {gold_delta}\n"
            f"⚙️ Delta Bạc: {silver_delta}\n"
            f"📡 Uptime: {self._price_count} updates received"
        )

    def _cmd_delta(self, args: list[str]):
        """
        Xem hoặc thay đổi delta.
        /delta            → xem hiện tại
        /delta gold 0.5%  → đặt delta vàng = 0.5%
        /delta silver 0.1 → đặt delta bạc = $0.1
        """
        if not args:
            # Xem delta hiện tại
            gold_delta = self._format_delta(self.config.delta_gold)
            silver_delta = self._format_delta(self.config.delta_silver)
            self.cmd_listener.reply(
                f"⚙️ Delta hiện tại:\n"
                f"🥇 Vàng: {gold_delta}\n"
                f"🥈 Bạc: {silver_delta}\n\n"
                f"Cách dùng:\n"
                f"/delta gold 0.5%\n"
                f"/delta silver 0.1"
            )
            return

        if len(args) < 2:
            self.cmd_listener.reply("❌ Cú pháp: /delta <gold|silver> <giá trị>\nVí dụ: /delta gold 0.5%")
            return

        symbol = args[0].lower()
        value_str = args[1]

        if symbol not in ("gold", "silver"):
            self.cmd_listener.reply("❌ Symbol phải là 'gold' hoặc 'silver'")
            return

        try:
            new_delta = Config._parse_delta(value_str)
        except (ValueError, TypeError):
            self.cmd_listener.reply(f"❌ Giá trị không hợp lệ: {value_str}")
            return

        # Cập nhật config in-memory + ghi file
        if symbol == "gold":
            self.config.delta_gold = new_delta
        else:
            self.config.delta_silver = new_delta
        self.config.save_to_file()

        formatted = self._format_delta(new_delta)
        self.cmd_listener.reply(
            f"✅ Đã cập nhật!\n"
            f"{'🥇 Vàng' if symbol == 'gold' else '🥈 Bạc'}: delta = {formatted}"
        )
        logger.info(f"Delta {symbol} updated via Telegram: {new_delta}")

    def _cmd_help(self, args: list[str]):
        """Hiển thị danh sách commands"""
        self.cmd_listener.reply(
            "📋 Commands:\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "/status — Xem giá hiện tại + config\n"
            "/delta — Xem delta hiện tại\n"
            "/delta gold 0.5% — Đặt delta vàng\n"
            "/delta silver 0.1 — Đặt delta bạc\n"
            "/help — Hiển thị help này"
        )

    @staticmethod
    def _format_delta(delta: dict) -> str:
        if delta["type"] == "percent":
            return f"{delta['value'] * 100:.2f}%"
        else:
            return f"${delta['value']:,.2f}"

    # ── Price callback ────────────────────────────────

    def _on_price_update(self, price_data: PriceData):
        """Callback khi nhận giá mới từ WebSocket"""
        self._price_count += 1
        self._latest_price = price_data

        # Gửi giá hiện tại khi khởi động
        if not self._startup_sent:
            self._startup_sent = True
            self.dispatcher.send_message(
                f"📊 Giá hiện tại:\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🥇 Vàng (XAU): ${price_data.gold:,.2f}\n"
                f"🥈 Bạc (XAG): ${price_data.silver:,.4f}\n"
                f"⚖️ Gold/Silver Ratio: {price_data.ratio}\n"
                f"🕐 {price_data.timestamp.strftime('%H:%M:%S %d/%m/%Y')}"
            )

        # Log mỗi 10 lần
        if self._price_count % 10 == 0:
            logger.info(
                f"[#{self._price_count}] "
                f"XAU: ${price_data.gold:,.2f} | "
                f"XAG: ${price_data.silver:,.4f} | "
                f"Ratio: {price_data.ratio}"
            )

        # Kiểm tra alerts
        alerts = self.alert_engine.check(price_data)
        for alert in alerts:
            self.dispatcher.send_alert(alert)

    # ── Run ────────────────────────────────

    async def run(self):
        """Chạy bot — WebSocket + Command polling + Heartbeat"""
        # Gửi startup message
        self.dispatcher.send_message(
            "🤖 Gold/Silver NotiBot đã khởi động!\n"
            f"📊 Delta: {self._format_delta(self.config.delta_gold)} (Gold), "
            f"{self._format_delta(self.config.delta_silver)} (Silver)\n"
            f"📣 Channels: {', '.join(self.config.channels)}\n"
            f"💬 Commands: /status /delta /help"
        )

        try:
            # Chạy song song: WebSocket + Command listener + Heartbeat
            await asyncio.gather(
                self.price_fetcher.start(),
                self._command_loop(),
                self._heartbeat_loop(),
            )
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        except Exception as e:
            logger.error(f"Bot error: {e}", exc_info=True)
            self.dispatcher.send_message(f"❌ Bot error: {e}")
        finally:
            await self.price_fetcher.stop()
            self.dispatcher.send_message("🛑 Gold/Silver NotiBot đã dừng.")
            logger.info("Bot stopped.")

    async def _command_loop(self):
        """Polling Telegram commands mỗi 3 giây (non-blocking)"""
        logger.info("Telegram command listener started")
        while True:
            try:
                # Chạy blocking HTTP request trong thread riêng để không block event loop
                updates = await asyncio.to_thread(self.cmd_listener.poll_once)
                if updates:
                    self.cmd_listener.process_updates(updates)
            except Exception as e:
                logger.warning(f"Command loop error: {e}")
            await asyncio.sleep(1)

    async def _heartbeat_loop(self):
        """Gửi heartbeat mỗi 1 giờ"""
        logger.info("Heartbeat started (every 1 hour)")
        while True:
            await asyncio.sleep(3600)  # 1 giờ
            try:
                now = datetime.now().strftime("%H:%M:%S %d/%m/%Y")
                price_info = ""
                if self._latest_price:
                    p = self._latest_price
                    price_info = (
                        f"\n🥇 XAU: ${p.gold:,.2f} | 🥈 XAG: ${p.silver:,.4f}\n"
                        f"⚖️ Ratio: {p.ratio}"
                    )
                self.dispatcher.send_message(
                    f"❤️ Bot đang hoạt động{price_info}\n"
                    f"📡 {self._price_count} updates | 🕐 {now}"
                )
                logger.info(f"Heartbeat sent ({self._price_count} updates)")
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")


def main():
    """Entry point"""
    project_root = Path(__file__).parent.parent
    config_path = str(project_root / "config.json")
    env_path = str(project_root / ".env")

    bot = NotiBot(config_path=config_path, env_path=env_path)

    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        logger.info("Shutting down...")


if __name__ == "__main__":
    main()
