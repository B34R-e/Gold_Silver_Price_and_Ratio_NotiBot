"""
Alert Engine — delta-based alert logic for Oil, Gold, Silver, Gold/Silver Ratio, Oil×Silver
"""
import logging
from datetime import datetime
from typing import Optional

from src.config import Config, ALL_SYMBOLS
from src.models import PriceData, Alert

logger = logging.getLogger(__name__)


class AlertEngine:
    """
    So sánh giá hiện tại với giá thông báo gần nhất.
    Nếu biến động ≥ delta X → tạo Alert.
    Sau khi alert, cập nhật lastNotifiedPrice = currentPrice.

    Hỗ trợ: oil, gold, silver, gold_silver_ratio, oil_x_silver
    """

    def __init__(self, config: Config):
        self.config = config

        # Giá được thông báo gần nhất cho mỗi symbol (in-memory)
        self._last_notified: dict[str, Optional[float]] = {
            symbol: None for symbol in ALL_SYMBOLS
        }

    def _get_price(self, symbol: str, price_data: PriceData) -> float:
        """Lấy giá tương ứng với symbol từ PriceData"""
        return getattr(price_data, symbol, 0.0)

    def check(self, price_data: PriceData) -> list[Alert]:
        """
        Kiểm tra tất cả symbols xem có biến động đủ ngưỡng không.

        Args:
            price_data: dữ liệu giá hiện tại

        Returns:
            Danh sách Alert (có thể rỗng)
        """
        alerts: list[Alert] = []

        for symbol in ALL_SYMBOLS:
            current_price = self._get_price(symbol, price_data)
            if current_price <= 0:
                continue

            # Lần đầu nhận giá → set baseline, không alert
            if self._last_notified[symbol] is None:
                self._last_notified[symbol] = current_price
                logger.info(f"{symbol} baseline set: {current_price:,.2f}")
                continue

            alert = self._check_symbol(
                symbol=symbol,
                current_price=current_price,
                last_notified=self._last_notified[symbol],
                timestamp=price_data.timestamp,
            )
            if alert:
                self._last_notified[symbol] = current_price
                alerts.append(alert)

        return alerts

    def _check_symbol(
        self,
        symbol: str,
        current_price: float,
        last_notified: float,
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
                timestamp=timestamp,
            )
            logger.info(
                f"ALERT: {symbol} changed {change:+,.2f} ({change_percent:+.2f}%) "
                f"from {last_notified:,.2f} to {current_price:,.2f}"
            )
            return alert

        return None
