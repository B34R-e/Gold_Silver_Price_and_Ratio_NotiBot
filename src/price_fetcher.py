"""
Price Fetcher — nhận giá XAUUSDT + XAGUSDT realtime qua Binance Futures WebSocket
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Callable, Optional

import websockets

from src.models import PriceData

logger = logging.getLogger(__name__)


class PriceFetcher:
    """
    Nhận giá vàng (XAUUSDT) và bạc (XAGUSDT) từ Binance Futures WebSocket.
    Tính Gold/Silver Ratio (làm tròn 1 decimal).
    Gọi callback mỗi khi có giá mới.

    Dùng raw WebSocket tới Binance fstream endpoint (ổn định hơn python-binance wrapper).
    """

    GOLD_SYMBOL = "xauusdt"
    SILVER_SYMBOL = "xagusdt"
    WS_BASE_URL = "wss://fstream.binance.com/ws"

    def __init__(self, on_price_update: Callable[[PriceData], None]):
        self.on_price_update = on_price_update
        self._running = False

        # Latest prices
        self._gold_price: float = 0.0
        self._silver_price: float = 0.0

    async def start(self):
        """Kết nối WebSocket và nhận giá realtime"""
        self._running = True

        # Subscribe cả 2 symbols trong 1 connection (combined stream)
        stream_url = f"{self.WS_BASE_URL}/{self.GOLD_SYMBOL}@ticker/{self.SILVER_SYMBOL}@ticker"
        logger.info(f"Connecting to Binance Futures WebSocket...")
        logger.info(f"Stream URL: {stream_url}")

        while self._running:
            try:
                async with websockets.connect(stream_url, ping_interval=20) as ws:
                    logger.info("WebSocket connected! Receiving price data...")
                    while self._running:
                        raw = await ws.recv()
                        msg = json.loads(raw)
                        self._handle_ticker(msg)
            except websockets.ConnectionClosed as e:
                if not self._running:
                    break
                logger.warning(f"WebSocket closed: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)
            except Exception as e:
                if not self._running:
                    break
                logger.warning(f"WebSocket error: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)

    def _handle_ticker(self, msg: dict):
        """Xử lý ticker message, cập nhật giá, tính ratio, gọi callback"""
        try:
            event_type = msg.get("e", "")
            if event_type != "24hrTicker":
                # Log unexpected messages for debugging
                logger.debug(f"Non-ticker message: {msg}")
                return

            symbol = msg.get("s", "").lower()
            price = float(msg.get("c", 0))  # 'c' = last/close price

            if price <= 0:
                return

            if symbol == self.GOLD_SYMBOL:
                self._gold_price = price
                logger.debug(f"Gold price updated: ${price:,.2f}")
            elif symbol == self.SILVER_SYMBOL:
                self._silver_price = price
                logger.debug(f"Silver price updated: ${price:,.4f}")
            else:
                return

            # Chỉ gọi callback khi đã có cả 2 giá
            if self._gold_price > 0 and self._silver_price > 0:
                price_data = PriceData(
                    gold=self._gold_price,
                    silver=self._silver_price,
                    timestamp=datetime.now(),
                )
                price_data.calculate_ratio()
                self.on_price_update(price_data)

        except (ValueError, TypeError, KeyError) as e:
            logger.warning(f"Error parsing ticker: {e} | msg: {msg}")

    async def stop(self):
        """Dừng WebSocket"""
        logger.info("Stopping Price Fetcher...")
        self._running = False
        logger.info("Price Fetcher stopped.")
