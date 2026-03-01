"""
Data models — PriceData, Alert
"""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PriceData:
    """Dữ liệu giá nhận từ Binance WebSocket"""
    gold: float = 0.0       # XAUUSDT price
    silver: float = 0.0     # XAGUSDT price
    ratio: float = 0.0      # Gold/Silver ratio (1 decimal)
    timestamp: datetime = field(default_factory=datetime.now)

    def calculate_ratio(self) -> float:
        """Tính Gold/Silver Ratio, làm tròn 1 chữ số thập phân"""
        if self.silver > 0:
            self.ratio = round(self.gold / self.silver, 1)
        else:
            self.ratio = 0.0
        return self.ratio


@dataclass
class Alert:
    """Thông báo khi giá biến động đủ ngưỡng"""
    symbol: str                    # 'gold' hoặc 'silver'
    current_price: float           # Giá hiện tại
    last_notified_price: float     # Giá lần thông báo gần nhất
    change: float                  # Biến động (current - last)
    change_percent: float          # Biến động %
    ratio: float                   # Gold/Silver ratio hiện tại
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def direction(self) -> str:
        """Hướng biến động: ▲ hoặc ▼"""
        return "▲" if self.change > 0 else "▼"

    @property
    def symbol_display(self) -> str:
        """Tên hiển thị: Vàng hoặc Bạc"""
        return "🥇 Vàng (XAU)" if self.symbol == "gold" else "🥈 Bạc (XAG)"

    def format_message(self) -> str:
        """Format thông báo gửi đến kênh messaging"""
        sign = "+" if self.change > 0 else ""
        time_str = self.timestamp.strftime("%H:%M:%S %d/%m/%Y")

        return (
            f"{self.symbol_display} {self.direction}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 Giá: ${self.current_price:,.2f}\n"
            f"📊 Biến động: {sign}{self.change:,.2f} ({sign}{self.change_percent:.2f}%)\n"
            f"📍 Giá trước: ${self.last_notified_price:,.2f}\n"
            f"⚖️ Gold/Silver Ratio: {self.ratio}\n"
            f"🕐 {time_str}"
        )
