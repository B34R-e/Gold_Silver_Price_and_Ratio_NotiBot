"""
Price Fetcher — nhận giá Oil (Yahoo Finance) + Gold/Silver (Binance Futures WebSocket)
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Callable, Optional

import websockets
import yfinance as yf

from src.models import PriceData

logger = logging.getLogger(__name__)


class PriceFetcher:
    """
    Nhận giá:
      - Oil (WTI): Yahoo Finance REST polling (mỗi 30s)
      - Gold (XAUUSDT) + Silver (XAGUSDT): Binance Futures WebSocket (realtime)

    Tính Gold/Silver Ratio + Oil × Silver.
    Gọi callback mỗi khi có giá mới (cần cả 3 giá).
    """

    GOLD_SYMBOL = "xauusdt"
    SILVER_SYMBOL = "xagusdt"
    OIL_TICKER = "CL=F"  # WTI Crude Oil Futures (Yahoo Finance)
    WS_BASE_URL = "wss://fstream.binance.com/ws"
    OIL_POLL_INTERVAL = 30  # seconds

    def __init__(self, on_price_update: Callable[[PriceData], None]):
        self.on_price_update = on_price_update
        self._running = False

        # Latest prices
        self._oil_price: float = 0.0
        self._gold_price: float = 0.0
        self._silver_price: float = 0.0

    async def start(self):
        """Chạy song song: Binance WebSocket + Yahoo Finance polling"""
        self._running = True
        await asyncio.gather(
            self._binance_ws_loop(),
            self._oil_polling_loop(),
        )

    async def _binance_ws_loop(self):
        """Kết nối Binance WebSocket cho Gold + Silver"""
        stream_url = f"{self.WS_BASE_URL}/{self.GOLD_SYMBOL}@ticker/{self.SILVER_SYMBOL}@ticker"
        logger.info(f"Connecting to Binance Futures WebSocket...")
        logger.info(f"Stream URL: {stream_url}")

        while self._running:
            try:
                async with websockets.connect(stream_url, ping_interval=20) as ws:
                    logger.info("Binance WebSocket connected! Receiving Gold/Silver prices...")
                    while self._running:
                        raw = await ws.recv()
                        msg = json.loads(raw)
                        self._handle_binance_ticker(msg)
            except websockets.ConnectionClosed as e:
                if not self._running:
                    break
                logger.warning(f"Binance WebSocket closed: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)
            except Exception as e:
                if not self._running:
                    break
                logger.warning(f"Binance WebSocket error: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5)

    async def _oil_polling_loop(self):
        """Polling giá dầu WTI từ Yahoo Finance"""
        logger.info(f"Oil price polling started (every {self.OIL_POLL_INTERVAL}s, ticker: {self.OIL_TICKER})")

        while self._running:
            try:
                # Chạy yfinance trong thread riêng (blocking I/O)
                oil_price = await asyncio.to_thread(self._fetch_oil_price)
                if oil_price and oil_price > 0:
                    self._oil_price = oil_price
                    logger.debug(f"Oil price updated: ${oil_price:,.2f}")
                    self._emit_price_update()
            except Exception as e:
                logger.warning(f"Oil polling error: {e}")

            await asyncio.sleep(self.OIL_POLL_INTERVAL)

    def _fetch_oil_price(self) -> Optional[float]:
        """Lấy giá dầu WTI từ Yahoo Finance (blocking)"""
        try:
            ticker = yf.Ticker(self.OIL_TICKER)
            # fast_info cho giá realtime nhất
            price = ticker.fast_info.get("lastPrice", 0)
            if price and price > 0:
                return float(price)

            # Fallback: lấy từ history
            hist = ticker.history(period="1d")
            if not hist.empty:
                return float(hist["Close"].iloc[-1])

            return None
        except Exception as e:
            logger.warning(f"Yahoo Finance error: {e}")
            return None

    def _handle_binance_ticker(self, msg: dict):
        """Xử lý Binance ticker message cho Gold/Silver"""
        try:
            event_type = msg.get("e", "")
            if event_type != "24hrTicker":
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

            self._emit_price_update()

        except (ValueError, TypeError, KeyError) as e:
            logger.warning(f"Error parsing Binance ticker: {e} | msg: {msg}")

    def _emit_price_update(self):
        """Gọi callback khi đã có đủ giá (cả 3)"""
        if self._gold_price > 0 and self._silver_price > 0 and self._oil_price > 0:
            price_data = PriceData(
                oil=self._oil_price,
                gold=self._gold_price,
                silver=self._silver_price,
                timestamp=datetime.now(),
            )
            price_data.calculate_derived()
            self.on_price_update(price_data)

    async def stop(self):
        """Dừng tất cả"""
        logger.info("Stopping Price Fetcher...")
        self._running = False
        logger.info("Price Fetcher stopped.")
