"""
Unit tests for Alert Engine — Oil, Gold, Silver, Gold/Silver Ratio, Oil×Silver
"""
import json
import os
import tempfile
from datetime import datetime

from src.config import Config
from src.models import PriceData
from src.alert_engine import AlertEngine


def _make_config(**deltas) -> Config:
    """Helper: tạo Config với delta tùy chỉnh"""
    delta_data = {
        "oil": deltas.get("oil", "1%"),
        "gold": deltas.get("gold", "0.25%"),
        "silver": deltas.get("silver", "0.25%"),
        "gold_silver_ratio": deltas.get("gold_silver_ratio", "1%"),
        "oil_x_silver": deltas.get("oil_x_silver", "1%"),
    }
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump({"delta": delta_data, "channels": []}, f)
    f.close()
    config = Config(config_path=f.name, env_path="nonexistent.env")
    os.unlink(f.name)
    return config


def _make_price(oil=70.0, gold=2000.0, silver=25.0) -> PriceData:
    """Helper: tạo PriceData với derived calculations"""
    p = PriceData(oil=oil, gold=gold, silver=silver, timestamp=datetime.now())
    p.calculate_derived()
    return p


class TestAlertEngine:

    def test_first_price_sets_baseline_no_alert(self):
        """Lần đầu nhận giá → set baseline, không alert"""
        engine = AlertEngine(_make_config())
        alerts = engine.check(_make_price())
        assert len(alerts) == 0

    def test_small_change_no_alert(self):
        """Biến động nhỏ hơn threshold → không alert"""
        engine = AlertEngine(_make_config(gold="0.25%"))

        engine.check(_make_price())

        # Gold change = $3 < threshold $5 (2000 * 0.0025) → no alert
        alerts = engine.check(_make_price(gold=2003.0))
        assert len(alerts) == 0

    def test_gold_large_change_triggers_alert(self):
        """Gold biến động ≥ threshold → alert"""
        engine = AlertEngine(_make_config(gold="0.25%"))

        engine.check(_make_price())

        # Gold change = $10 ≥ threshold $5 → alert
        alerts = engine.check(_make_price(gold=2010.0))
        gold_alerts = [a for a in alerts if a.symbol == "gold"]
        assert len(gold_alerts) == 1
        assert gold_alerts[0].current_price == 2010.0
        assert gold_alerts[0].last_notified_price == 2000.0
        assert gold_alerts[0].change == 10.0

    def test_oil_alert(self):
        """Oil biến động ≥ threshold → alert"""
        engine = AlertEngine(_make_config(oil="1%"))

        engine.check(_make_price(oil=70.0))

        # Oil change = $1 ≥ threshold $0.70 (70 * 0.01) → alert
        alerts = engine.check(_make_price(oil=71.0))
        oil_alerts = [a for a in alerts if a.symbol == "oil"]
        assert len(oil_alerts) == 1
        assert oil_alerts[0].current_price == 71.0

    def test_gold_silver_ratio_alert(self):
        """Gold/Silver Ratio biến động → alert"""
        engine = AlertEngine(_make_config(gold_silver_ratio=0.5))

        # Baseline ratio = 2000/25 = 80.0
        engine.check(_make_price(gold=2000.0, silver=25.0))

        # New ratio = 2020/25 = 80.8 → change = 0.8 ≥ 0.5 → alert
        alerts = engine.check(_make_price(gold=2020.0, silver=25.0))
        ratio_alerts = [a for a in alerts if a.symbol == "gold_silver_ratio"]
        assert len(ratio_alerts) == 1

    def test_oil_x_silver_alert(self):
        """Oil × Silver biến động → alert"""
        engine = AlertEngine(_make_config(oil_x_silver="1%"))

        # Baseline: 70 * 25 = 1750
        engine.check(_make_price(oil=70.0, silver=25.0))

        # New: 72 * 25 = 1800 → change = 50 (2.86%) ≥ 1% → alert
        alerts = engine.check(_make_price(oil=72.0, silver=25.0))
        oxs_alerts = [a for a in alerts if a.symbol == "oil_x_silver"]
        assert len(oxs_alerts) == 1

    def test_alert_updates_last_notified(self):
        """Sau alert, lastNotifiedPrice phải cập nhật"""
        engine = AlertEngine(_make_config(gold="0.25%"))

        engine.check(_make_price(gold=2000.0))

        # Jump to 2010 → alert (baseline becomes 2010)
        alerts1 = engine.check(_make_price(gold=2010.0))
        gold_alerts1 = [a for a in alerts1 if a.symbol == "gold"]
        assert len(gold_alerts1) == 1

        # Small change from 2010 → 2013 → no alert (threshold = 2010 * 0.0025 ≈ 5.025)
        alerts2 = engine.check(_make_price(gold=2013.0))
        gold_alerts2 = [a for a in alerts2 if a.symbol == "gold"]
        assert len(gold_alerts2) == 0

    def test_absolute_delta(self):
        """Test delta dạng absolute number"""
        engine = AlertEngine(_make_config(gold=50))

        engine.check(_make_price(gold=2000.0))

        # Change = $30 < $50 threshold → no alert
        alerts1 = engine.check(_make_price(gold=2030.0))
        gold_alerts1 = [a for a in alerts1 if a.symbol == "gold"]
        assert len(gold_alerts1) == 0

        # Change = $60 from baseline ≥ $50 threshold → alert
        alerts2 = engine.check(_make_price(gold=2060.0))
        gold_alerts2 = [a for a in alerts2 if a.symbol == "gold"]
        assert len(gold_alerts2) == 1

    def test_downward_alert(self):
        """Test alert khi giá giảm"""
        engine = AlertEngine(_make_config(gold="0.25%"))

        engine.check(_make_price(gold=2000.0))

        # Giảm $10 → alert
        alerts = engine.check(_make_price(gold=1990.0))
        gold_alerts = [a for a in alerts if a.symbol == "gold"]
        assert len(gold_alerts) == 1
        assert gold_alerts[0].change < 0
        assert gold_alerts[0].direction == "▼"

    def test_multiple_symbols_alert_simultaneously(self):
        """Nhiều symbols cùng alert"""
        engine = AlertEngine(_make_config(oil="1%", gold="0.25%", silver="0.25%"))

        engine.check(_make_price(oil=70.0, gold=2000.0, silver=25.0))

        # All three change significantly
        alerts = engine.check(_make_price(oil=72.0, gold=2020.0, silver=26.0))
        symbols = {a.symbol for a in alerts}
        assert "oil" in symbols
        assert "gold" in symbols
        assert "silver" in symbols
