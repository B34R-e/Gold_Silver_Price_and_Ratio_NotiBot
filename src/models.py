"""
Data models — PriceData, Alert
"""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PriceData:
    """Dữ liệu giá từ Binance WebSocket + Yahoo Finance"""
    oil: float = 0.0        # CL=F (WTI Crude Oil) price
    gold: float = 0.0       # XAUUSDT price
    silver: float = 0.0     # XAGUSDT price
    gold_silver_ratio: float = 0.0   # Gold/Silver ratio (1 decimal)
    oil_x_silver: float = 0.0       # Oil × Silver
    timestamp: datetime = field(default_factory=datetime.now)

    def calculate_derived(self):
        """Tính Gold/Silver Ratio và Oil × Silver"""
        if self.silver > 0:
            self.gold_silver_ratio = round(self.gold / self.silver, 1)
        else:
            self.gold_silver_ratio = 0.0

        if self.oil > 0 and self.silver > 0:
            self.oil_x_silver = round(self.oil * self.silver, 2)
        else:
            self.oil_x_silver = 0.0


# Symbol metadata for display
SYMBOL_INFO = {
    "oil": {"emoji": "🛢️", "name": "Dầu (WTI)", "decimals": 2},
    "gold": {"emoji": "🥇", "name": "Vàng (XAU)", "decimals": 2},
    "silver": {"emoji": "🥈", "name": "Bạc (XAG)", "decimals": 4},
    "gold_silver_ratio": {"emoji": "⚖️", "name": "Gold/Silver Ratio", "decimals": 1},
    "oil_x_silver": {"emoji": "📐", "name": "Oil × Silver", "decimals": 2},
}


@dataclass
class Alert:
    """Thông báo khi giá biến động đủ ngưỡng"""
    symbol: str                    # 'oil', 'gold', 'silver', 'gold_silver_ratio', 'oil_x_silver'
    current_price: float           # Giá hiện tại
    last_notified_price: float     # Giá lần thông báo gần nhất
    change: float                  # Biến động (current - last)
    change_percent: float          # Biến động %
    gold_silver_ratio: float = 0.0 # G/S ratio hiện tại (dùng cho silver alert)
    oil_x_silver: float = 0.0     # O×S hiện tại (dùng cho silver alert)
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def direction(self) -> str:
        """Hướng biến động: ▲ hoặc ▼"""
        return "▲" if self.change > 0 else "▼"

    @property
    def symbol_display(self) -> str:
        """Tên hiển thị với emoji"""
        info = SYMBOL_INFO.get(self.symbol, {})
        return f"{info.get('emoji', '📊')} {info.get('name', self.symbol)}"

    @property
    def price_decimals(self) -> int:
        info = SYMBOL_INFO.get(self.symbol, {})
        return info.get("decimals", 2)

    def format_message(self) -> str:
        """Format thông báo gửi đến kênh messaging"""
        sign = "+" if self.change > 0 else ""
        time_str = self.timestamp.strftime("%H:%M:%S %d/%m/%Y")
        d = self.price_decimals

        # Dòng biến động — silver ghi chung G/S ratio và O×S
        change_line = f"📊 Biến động: {sign}{self.change:,.{d}f} ({sign}{self.change_percent:.2f}%)"
        if self.symbol == "silver":
            change_line += f" | ⚖️ G/S: {self.gold_silver_ratio} | 📐 O×S: {self.oil_x_silver:,.2f}"

        return (
            f"{self.symbol_display} {self.direction}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 Giá: {self.current_price:,.{d}f}\n"
            f"{change_line}\n"
            f"📍 Giá trước: {self.last_notified_price:,.{d}f}\n"
            f"🕐 {time_str}"
        )
