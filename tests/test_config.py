"""
Unit tests for Config Manager
"""
import json
import os
import tempfile
import pytest

from src.config import Config, ALL_SYMBOLS


class TestDeltaParsing:
    """Test delta parsing: %, absolute"""

    def test_parse_percent(self):
        result = Config._parse_delta("0.25%")
        assert result["type"] == "percent"
        assert abs(result["value"] - 0.0025) < 1e-10

    def test_parse_percent_1(self):
        result = Config._parse_delta("1%")
        assert result["type"] == "percent"
        assert abs(result["value"] - 0.01) < 1e-10

    def test_parse_absolute_number(self):
        result = Config._parse_delta(50)
        assert result["type"] == "absolute"
        assert result["value"] == 50.0

    def test_parse_absolute_string(self):
        result = Config._parse_delta("50")
        assert result["type"] == "absolute"
        assert result["value"] == 50.0


class TestConfig:
    """Test config loading"""

    def _create_config(self, data: dict) -> str:
        """Helper: tạo temp config file"""
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(data, f)
        f.close()
        return f.name

    def test_load_config_with_all_symbols(self):
        path = self._create_config({
            "delta": {
                "oil": "1%",
                "gold": "0.25%",
                "silver": 0.1,
                "gold_silver_ratio": 0.5,
                "oil_x_silver": "1%",
            },
            "channels": ["telegram", "discord"],
        })
        try:
            config = Config(config_path=path, env_path="nonexistent.env")
            assert config.deltas["gold"]["type"] == "percent"
            assert abs(config.deltas["gold"]["value"] - 0.0025) < 1e-10
            assert config.deltas["oil"]["type"] == "percent"
            assert config.deltas["silver"]["type"] == "absolute"
            assert config.deltas["silver"]["value"] == 0.1
            assert config.deltas["gold_silver_ratio"]["type"] == "absolute"
            assert config.deltas["gold_silver_ratio"]["value"] == 0.5
            assert config.deltas["oil_x_silver"]["type"] == "percent"
            assert config.channels == ["telegram", "discord"]
        finally:
            os.unlink(path)

    def test_load_missing_symbols_get_default(self):
        """Symbols không có trong config sẽ dùng default 1%"""
        path = self._create_config({
            "delta": {"gold": "0.5%"},
            "channels": ["telegram"],
        })
        try:
            config = Config(config_path=path, env_path="nonexistent.env")
            assert config.deltas["gold"]["type"] == "percent"
            assert abs(config.deltas["gold"]["value"] - 0.005) < 1e-10
            # Missing symbols default to 1%
            assert config.deltas["oil"]["type"] == "percent"
            assert abs(config.deltas["oil"]["value"] - 0.01) < 1e-10
            assert config.deltas["silver"]["type"] == "percent"
            assert config.deltas["oil_x_silver"]["type"] == "percent"
        finally:
            os.unlink(path)

    def test_get_delta_threshold_percent(self):
        path = self._create_config({
            "delta": {"gold": "0.25%"},
            "channels": [],
        })
        try:
            config = Config(config_path=path, env_path="nonexistent.env")
            # Gold at $2000 → threshold = 2000 * 0.0025 = $5
            threshold = config.get_delta_threshold("gold", 2000.0)
            assert abs(threshold - 5.0) < 0.01
        finally:
            os.unlink(path)

    def test_get_delta_threshold_absolute(self):
        path = self._create_config({
            "delta": {"gold": 50, "silver": 1},
            "channels": [],
        })
        try:
            config = Config(config_path=path, env_path="nonexistent.env")
            threshold = config.get_delta_threshold("gold", 2000.0)
            assert threshold == 50.0
        finally:
            os.unlink(path)

    def test_get_delta_threshold_oil(self):
        path = self._create_config({
            "delta": {"oil": "1%"},
            "channels": [],
        })
        try:
            config = Config(config_path=path, env_path="nonexistent.env")
            # Oil at $70 → threshold = 70 * 0.01 = $0.70
            threshold = config.get_delta_threshold("oil", 70.0)
            assert abs(threshold - 0.70) < 0.01
        finally:
            os.unlink(path)

    def test_all_symbols_defined(self):
        """Verify ALL_SYMBOLS contains expected entries"""
        assert "oil" in ALL_SYMBOLS
        assert "gold" in ALL_SYMBOLS
        assert "silver" in ALL_SYMBOLS
        assert "gold_silver_ratio" in ALL_SYMBOLS
        assert "oil_x_silver" in ALL_SYMBOLS

    def test_missing_config_file(self):
        with pytest.raises(FileNotFoundError):
            Config(config_path="nonexistent.json", env_path="nonexistent.env")
