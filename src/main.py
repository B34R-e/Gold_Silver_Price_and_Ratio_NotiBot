"""
Oil/Gold/Silver Price & Ratio NotiBot — Main Entry Point

Bot nhận giá Oil (Yahoo Finance), Gold + Silver (Binance Futures WebSocket),
tính Gold/Silver Ratio và Oil×Silver, gửi thông báo qua Telegram + Discord khi giá biến động ≥ X.
"""
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

from src.config import Config, ALL_SYMBOLS
from src.models import PriceData, SYMBOL_INFO
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
        logger.info("Oil/Gold/Silver NotiBot starting...")
        logger.info("=" * 50)

        # Load config
        self.config = Config(config_path=config_path, env_path=env_path)
        for symbol in ALL_SYMBOLS:
            logger.info(f"Delta {symbol}: {self.config.deltas[symbol]}")
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
        stats = self.dispatcher.stats

        # Build delta info
        delta_lines = []
        for symbol in ALL_SYMBOLS:
            delta_lines.append(f"  {symbol}: {self._format_delta(self.config.deltas[symbol])}")
        delta_str = "\n".join(delta_lines)

        self.cmd_listener.reply(
            f"📊 Trạng thái NotiBot\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🛢️ Dầu (WTI): ${p.oil:,.2f}\n"
            f"🥇 Vàng (XAU): ${p.gold:,.2f}\n"
            f"🥈 Bạc (XAG): ${p.silver:,.4f}\n"
            f"⚖️ Gold/Silver Ratio: {p.gold_silver_ratio}\n"
            f"📐 Oil × Silver: {p.oil_x_silver:,.2f}\n"
            f"🕐 {p.timestamp.strftime('%H:%M:%S %d/%m/%Y')}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚙️ Delta:\n{delta_str}\n"
            f"📡 {self._price_count} updates | "
            f"📤 {stats['sent']} sent | ❌ {stats['failed']} failed | "
            f"📬 {self.dispatcher.queue_size} queued"
        )

    def _cmd_delta(self, args: list[str]):
        """
        Xem hoặc thay đổi delta.
        /delta                        → xem hiện tại
        /delta gold 0.5%              → đặt delta vàng = 0.5%
        /delta silver 0.1             → đặt delta bạc = $0.1
        /delta oil 1%                 → đặt delta dầu = 1%
        /delta gold_silver_ratio 0.5  → đặt delta ratio = 0.5
        /delta oil_x_silver 1%        → đặt delta oil×silver = 1%
        """
        if not args:
            # Xem delta hiện tại
            lines = []
            for symbol in ALL_SYMBOLS:
                info = SYMBOL_INFO.get(symbol, {})
                emoji = info.get("emoji", "📊")
                name = info.get("name", symbol)
                delta_str = self._format_delta(self.config.deltas[symbol])
                lines.append(f"{emoji} {name}: {delta_str}")
            self.cmd_listener.reply(
                f"⚙️ Delta hiện tại:\n" + "\n".join(lines) + "\n\n"
                f"Cách dùng:\n"
                f"/delta oil 1%\n"
                f"/delta gold 0.5%\n"
                f"/delta silver 0.1\n"
                f"/delta gold_silver_ratio 0.5\n"
                f"/delta oil_x_silver 1%"
            )
            return

        if len(args) < 2:
            self.cmd_listener.reply(
                f"❌ Cú pháp: /delta <symbol> <giá trị>\n"
                f"Symbols: {', '.join(ALL_SYMBOLS)}"
            )
            return

        symbol = args[0].lower()
        value_str = args[1]

        if symbol not in ALL_SYMBOLS:
            self.cmd_listener.reply(f"❌ Symbol phải là: {', '.join(ALL_SYMBOLS)}")
            return

        try:
            new_delta = Config._parse_delta(value_str)
        except (ValueError, TypeError):
            self.cmd_listener.reply(f"❌ Giá trị không hợp lệ: {value_str}")
            return

        # Cập nhật config in-memory + ghi file
        self.config.deltas[symbol] = new_delta
        self.config.save_to_file()

        info = SYMBOL_INFO.get(symbol, {})
        display_name = f"{info.get('emoji', '📊')} {info.get('name', symbol)}"
        formatted = self._format_delta(new_delta)
        self.cmd_listener.reply(f"✅ Đã cập nhật!\n{display_name}: delta = {formatted}")
        logger.info(f"Delta {symbol} updated via Telegram: {new_delta}")

    def _cmd_help(self, args: list[str]):
        """Hiển thị danh sách commands"""
        self.cmd_listener.reply(
            "📋 Commands:\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "/status — Xem giá hiện tại + config\n"
            "/delta — Xem delta hiện tại\n"
            "/delta <symbol> <value> — Đặt delta\n"
            f"  Symbols: {', '.join(ALL_SYMBOLS)}\n"
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
        """Callback khi nhận giá mới"""
        self._price_count += 1
        self._latest_price = price_data

        # Gửi giá hiện tại khi khởi động
        if not self._startup_sent:
            self._startup_sent = True
            self.dispatcher.send_message(
                f"📊 Giá hiện tại:\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🛢️ Dầu (WTI): ${price_data.oil:,.2f}\n"
                f"🥇 Vàng (XAU): ${price_data.gold:,.2f}\n"
                f"🥈 Bạc (XAG): ${price_data.silver:,.4f}\n"
                f"⚖️ Gold/Silver Ratio: {price_data.gold_silver_ratio}\n"
                f"📐 Oil × Silver: {price_data.oil_x_silver:,.2f}\n"
                f"🕐 {price_data.timestamp.strftime('%H:%M:%S %d/%m/%Y')}"
            )

        # Log mỗi 10 lần
        if self._price_count % 10 == 0:
            logger.info(
                f"[#{self._price_count}] "
                f"OIL: ${price_data.oil:,.2f} | "
                f"XAU: ${price_data.gold:,.2f} | "
                f"XAG: ${price_data.silver:,.4f} | "
                f"G/S: {price_data.gold_silver_ratio} | "
                f"O×S: {price_data.oil_x_silver:,.2f}"
            )

        # Kiểm tra alerts
        alerts = self.alert_engine.check(price_data)
        for alert in alerts:
            self.dispatcher.send_alert(alert)

    # ── Run ────────────────────────────────

    async def run(self):
        """Chạy bot — WebSocket + Oil polling + Command polling + Heartbeat"""
        # Khởi động notification worker (background thread)
        self.dispatcher.start_worker()

        # Build delta summary
        delta_parts = []
        for symbol in ALL_SYMBOLS:
            delta_parts.append(f"{symbol}: {self._format_delta(self.config.deltas[symbol])}")
        delta_summary = ", ".join(delta_parts)

        # Gửi startup message
        self.dispatcher.send_message_sync(
            f"🤖 Oil/Gold/Silver NotiBot đã khởi động!\n"
            f"📊 Delta: {delta_summary}\n"
            f"📣 Channels: {', '.join(self.config.channels)}\n"
            f"💬 Commands: /status /delta /help"
        )

        try:
            # Chạy song song: Price fetcher (WS + oil poll) + Command listener + Heartbeat
            await asyncio.gather(
                self.price_fetcher.start(),
                self._command_loop(),
                self._heartbeat_loop(),
            )
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        except Exception as e:
            logger.error(f"Bot error: {e}", exc_info=True)
            self.dispatcher.send_message_sync(f"❌ Bot error: {e}")
        finally:
            await self.price_fetcher.stop()
            self.dispatcher.send_message_sync("🛑 Oil/Gold/Silver NotiBot đã dừng.")
            self.dispatcher.stop_worker()
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
                        f"\n🛢️ OIL: ${p.oil:,.2f} | 🥇 XAU: ${p.gold:,.2f} | 🥈 XAG: ${p.silver:,.4f}\n"
                        f"⚖️ G/S: {p.gold_silver_ratio} | 📐 O×S: {p.oil_x_silver:,.2f}"
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
