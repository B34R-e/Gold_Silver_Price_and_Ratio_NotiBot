"""
Alert Engine — delta-based alert logic
"""
import logging
from datetime import datetime
from typing import Optional

from src.config import Config
from src.models import PriceData, Alert

logger = logging.getLogger(__name__)


class AlertEngine:
    """
    So sánh giá hiện tại với giá thông báo gần nhất.
    Nếu biến động ≥ delta X → tạo Alert.
    Sau khi alert, cập nhật lastNotifiedPrice = currentPrice.
    """

    def __init__(self, config: Config):
        self.config = config

        # Giá được thông báo gần nhất (in-memory, mất khi restart)
        self._last_notified_gold: Optional[float] = None
        self._last_notified_silver: Optional[float] = None

    def check(self, price_data: PriceData) -> list[Alert]:
        """
        Kiểm tra xem giá có biến động đủ ngưỡng không.

        Args:
            price_data: dữ liệu giá hiện tại

        Returns:
            Danh sách Alert (có thể rỗng, 1, hoặc 2 alerts)
        """
        alerts: list[Alert] = []

        # Lần đầu nhận giá → set baseline, không alert
        if self._last_notified_gold is None:
            self._last_notified_gold = price_data.gold
            logger.info(f"Gold baseline set: ${price_data.gold:,.2f}")

        if self._last_notified_silver is None:
            self._last_notified_silver = price_data.silver
            logger.info(f"Silver baseline set: ${price_data.silver:,.2f}")

        # Check gold
        gold_alert = self._check_symbol(
            symbol="gold",
            current_price=price_data.gold,
            last_notified=self._last_notified_gold,
            ratio=price_data.ratio,
            timestamp=price_data.timestamp,
        )
        if gold_alert:
            self._last_notified_gold = price_data.gold
            alerts.append(gold_alert)

        # Check silver
        silver_alert = self._check_symbol(
            symbol="silver",
            current_price=price_data.silver,
            last_notified=self._last_notified_silver,
            ratio=price_data.ratio,
            timestamp=price_data.timestamp,
        )
        if silver_alert:
            self._last_notified_silver = price_data.silver
            alerts.append(silver_alert)

        return alerts

    def _check_symbol(
        self,
        symbol: str,
        current_price: float,
        last_notified: float,
        ratio: float,
        timestamp: datetime,
    ) -> Optional[Alert]:
        """Kiểm tra 1 symbol cụ thể"""
        if last_notified <= 0:
            return None

        change = current_price - last_notified
        change_abs = abs(change)
        change_percent = (change / last_notified) * 100

        # Tính ngưỡng
        threshold = self.config.get_delta_threshold(symbol, last_notified)

        if change_abs >= threshold:
            alert = Alert(
                symbol=symbol,
                current_price=current_price,
                last_notified_price=last_notified,
                change=change,
                change_percent=change_percent,
                ratio=ratio,
                timestamp=timestamp,
            )
            logger.info(
                f"ALERT: {symbol} changed {change:+,.2f} ({change_percent:+.2f}%) "
                f"from ${last_notified:,.2f} to ${current_price:,.2f}"
            )
            return alert

        return None
