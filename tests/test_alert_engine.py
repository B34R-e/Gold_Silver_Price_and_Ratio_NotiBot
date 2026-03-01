"""
Unit tests for Alert Engine
"""
import json
import os
import tempfile
from datetime import datetime

from src.config import Config
from src.models import PriceData
from src.alert_engine import AlertEngine


def _make_config(gold_delta="0.25%", silver_delta="0.25%") -> Config:
    """Helper: tạo Config với delta tùy chỉnh"""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump({
        "delta": {"gold": gold_delta, "silver": silver_delta},
        "channels": [],
    }, f)
    f.close()
    config = Config(config_path=f.name, env_path="nonexistent.env")
    os.unlink(f.name)
    return config


class TestAlertEngine:

    def test_first_price_sets_baseline_no_alert(self):
        """Lần đầu nhận giá → set baseline, không alert"""
        engine = AlertEngine(_make_config())
        price = PriceData(gold=2000.0, silver=25.0, timestamp=datetime.now())
        price.calculate_ratio()

        alerts = engine.check(price)
        assert len(alerts) == 0

    def test_small_change_no_alert(self):
        """Biến động nhỏ hơn threshold → không alert"""
        engine = AlertEngine(_make_config("0.25%", "0.25%"))

        # Set baseline
        p1 = PriceData(gold=2000.0, silver=25.0, timestamp=datetime.now())
        p1.calculate_ratio()
        engine.check(p1)

        # Change < 0.25% (2000 * 0.0025 = 5) → change = $3 → no alert
        p2 = PriceData(gold=2003.0, silver=25.0, timestamp=datetime.now())
        p2.calculate_ratio()
        alerts = engine.check(p2)
        assert len(alerts) == 0

    def test_large_change_triggers_alert(self):
        """Biến động ≥ threshold → alert"""
        engine = AlertEngine(_make_config("0.25%", "0.25%"))

        # Set baseline
        p1 = PriceData(gold=2000.0, silver=25.0, timestamp=datetime.now())
        p1.calculate_ratio()
        engine.check(p1)

        # Change ≥ 0.25% (2000 * 0.0025 = 5) → change = $10 → alert!
        p2 = PriceData(gold=2010.0, silver=25.0, timestamp=datetime.now())
        p2.calculate_ratio()
        alerts = engine.check(p2)
        assert len(alerts) == 1
        assert alerts[0].symbol == "gold"
        assert alerts[0].current_price == 2010.0
        assert alerts[0].last_notified_price == 2000.0
        assert alerts[0].change == 10.0

    def test_alert_updates_last_notified(self):
        """Sau alert, lastNotifiedPrice phải cập nhật"""
        engine = AlertEngine(_make_config("0.25%", "0.25%"))

        # Baseline: 2000
        p1 = PriceData(gold=2000.0, silver=25.0, timestamp=datetime.now())
        p1.calculate_ratio()
        engine.check(p1)

        # Jump to 2010 → alert (baseline becomes 2010)
        p2 = PriceData(gold=2010.0, silver=25.0, timestamp=datetime.now())
        p2.calculate_ratio()
        alerts1 = engine.check(p2)
        assert len(alerts1) == 1

        # Small change from 2010 → 2013 → no alert (threshold = 2010 * 0.0025 = 5.025)
        p3 = PriceData(gold=2013.0, silver=25.0, timestamp=datetime.now())
        p3.calculate_ratio()
        alerts2 = engine.check(p3)
        assert len(alerts2) == 0

    def test_absolute_delta(self):
        """Test delta dạng absolute number"""
        engine = AlertEngine(_make_config(50, 1))

        # Baseline
        p1 = PriceData(gold=2000.0, silver=25.0, timestamp=datetime.now())
        p1.calculate_ratio()
        engine.check(p1)

        # Change = $30 < $50 threshold → no alert
        p2 = PriceData(gold=2030.0, silver=25.0, timestamp=datetime.now())
        p2.calculate_ratio()
        alerts1 = engine.check(p2)
        assert len(alerts1) == 0

        # Change = $60 from baseline ≥ $50 threshold → alert
        p3 = PriceData(gold=2060.0, silver=25.0, timestamp=datetime.now())
        p3.calculate_ratio()
        alerts2 = engine.check(p3)
        assert len(alerts2) == 1

    def test_downward_alert(self):
        """Test alert khi giá giảm"""
        engine = AlertEngine(_make_config("0.25%", "0.25%"))

        p1 = PriceData(gold=2000.0, silver=25.0, timestamp=datetime.now())
        p1.calculate_ratio()
        engine.check(p1)

        # Giảm $10 → alert
        p2 = PriceData(gold=1990.0, silver=25.0, timestamp=datetime.now())
        p2.calculate_ratio()
        alerts = engine.check(p2)
        assert len(alerts) == 1
        assert alerts[0].change < 0
        assert alerts[0].direction == "▼"

    def test_ratio_in_alert(self):
        """Test ratio trong alert"""
        engine = AlertEngine(_make_config("0.25%", "0.25%"))

        p1 = PriceData(gold=2000.0, silver=25.0, timestamp=datetime.now())
        p1.calculate_ratio()
        engine.check(p1)

        p2 = PriceData(gold=2010.0, silver=25.0, timestamp=datetime.now())
        p2.calculate_ratio()
        alerts = engine.check(p2)
        assert len(alerts) == 1
        assert alerts[0].ratio == 80.4  # 2010/25 = 80.4
