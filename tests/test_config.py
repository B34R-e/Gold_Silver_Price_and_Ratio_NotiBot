"""
Unit tests for Config Manager
"""
import json
import os
import tempfile
import pytest

from src.config import Config


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

    def test_load_default_config(self):
        path = self._create_config({
            "delta": {"gold": "0.25%", "silver": "0.25%"},
            "channels": ["telegram", "discord"],
        })
        try:
            config = Config(config_path=path, env_path="nonexistent.env")
            assert config.delta_gold["type"] == "percent"
            assert abs(config.delta_gold["value"] - 0.0025) < 1e-10
            assert config.channels == ["telegram", "discord"]
        finally:
            os.unlink(path)

    def test_load_absolute_delta(self):
        path = self._create_config({
            "delta": {"gold": 50, "silver": 1},
            "channels": ["telegram"],
        })
        try:
            config = Config(config_path=path, env_path="nonexistent.env")
            assert config.delta_gold["type"] == "absolute"
            assert config.delta_gold["value"] == 50.0
            assert config.delta_silver["value"] == 1.0
        finally:
            os.unlink(path)

    def test_get_delta_threshold_percent(self):
        path = self._create_config({
            "delta": {"gold": "0.25%", "silver": "0.25%"},
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

    def test_missing_config_file(self):
        with pytest.raises(FileNotFoundError):
            Config(config_path="nonexistent.json", env_path="nonexistent.env")
