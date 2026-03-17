package config

import (
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"strings"

	"github.com/joho/godotenv"
)

// Delta struct represents parsed delta configuration
type Delta struct {
	Type  string  // "percent" or "absolute"
	Value float64 // e.g. 0.0025 for 0.25%, or 50.0 for $50
}

// Config struct holds all configuration values
type Config struct {
	ConfigPath        string
	Deltas            map[string]Delta
	Channels          []string
	TelegramBotToken  string
	TelegramChatID    string
	DiscordWebhookURL string

	// Internal raw data for saving back exactly
	rawData map[string]interface{}
}

// AllSymbols supported for delta alerts
var AllSymbols = []string{"oil", "gold", "silver", "gold_silver_ratio", "oil_x_silver"}

// LoadConfig reads from config.json and .env
func LoadConfig(configPath, envPath string) (*Config, error) {
	// 1. Load .env if it exists
	if _, err := os.Stat(envPath); err == nil {
		godotenv.Load(envPath)
	}

	// 2. Load config.json
	cfg := &Config{
		ConfigPath: configPath,
		Deltas:     make(map[string]Delta),
	}

	fileContent, err := os.ReadFile(configPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read config file: %w", err)
	}

	var raw map[string]interface{}
	if err := json.Unmarshal(fileContent, &raw); err != nil {
		return nil, fmt.Errorf("failed to parse config.json: %w", err)
	}
	cfg.rawData = raw

	// Parse Deltas
	deltaRaw, ok := raw["delta"].(map[string]interface{})
	if !ok {
		deltaRaw = make(map[string]interface{}) // Default empty if not found
	}

	for _, symbol := range AllSymbols {
		val, exists := deltaRaw[symbol]
		if !exists {
			cfg.Deltas[symbol] = ParseDelta("1%") // default 1%
		} else {
			cfg.Deltas[symbol] = ParseDelta(val)
		}
	}

	// Parse Channels
	if chRaw, ok := raw["channels"].([]interface{}); ok {
		for _, ch := range chRaw {
			if chStr, ok := ch.(string); ok {
				cfg.Channels = append(cfg.Channels, chStr)
			}
		}
	} else {
		cfg.Channels = []string{"telegram", "discord"} // defaults
	}

	// Read secrets from environment variables
	cfg.TelegramBotToken = os.Getenv("TELEGRAM_BOT_TOKEN")
	cfg.TelegramChatID = os.Getenv("TELEGRAM_CHAT_ID")
	cfg.DiscordWebhookURL = os.Getenv("DISCORD_WEBHOOK_URL")

	return cfg, nil
}

// ParseDelta converts a raw config value (string "%" or float) to Delta struct
func ParseDelta(value interface{}) Delta {
	switch v := value.(type) {
	case string:
		if strings.HasSuffix(v, "%") {
			pctStr := strings.TrimSuffix(v, "%")
			pct, err := strconv.ParseFloat(pctStr, 64)
			if err == nil {
				return Delta{Type: "percent", Value: pct / 100.0}
			}
		}
		// Try parsing as absolute string
		abs, err := strconv.ParseFloat(v, 64)
		if err == nil {
			return Delta{Type: "absolute", Value: abs}
		}
	case float64:
		return Delta{Type: "absolute", Value: v}
	}
	// Fallback to default
	return Delta{Type: "percent", Value: 0.01}
}

// FormatDelta converts Delta back to config.json representation
func FormatDeltaToConfig(d Delta) interface{} {
	if d.Type == "percent" {
		// remove insignificant trailing zeros manually or use %f
		s := fmt.Sprintf("%f", d.Value*100)
		s = strings.TrimRight(s, "0")
		s = strings.TrimRight(s, ".")
		return s + "%"
	}
	return d.Value
}

// SaveToFile writes the current in-memory delta config back to config.json
func (c *Config) SaveToFile() error {
	deltaOut := make(map[string]interface{})
	for symbol, d := range c.Deltas {
		deltaOut[symbol] = FormatDeltaToConfig(d)
	}
	c.rawData["delta"] = deltaOut

	bytes, err := json.MarshalIndent(c.rawData, "", "  ") // use 2 spaces for format
	if err != nil {
		return fmt.Errorf("failed to marshal config: %w", err)
	}

	if err := os.WriteFile(c.ConfigPath, bytes, 0644); err != nil {
		return fmt.Errorf("failed to write config file: %w", err)
	}
	return nil
}

// GetDeltaThreshold returns the absolute threshold change required for an alert
func (c *Config) GetDeltaThreshold(symbol string, currentPrice float64) float64 {
	d, exists := c.Deltas[symbol]
	if !exists {
		d = Delta{Type: "percent", Value: 0.01}
	}

	if d.Type == "percent" {
		return currentPrice * d.Value
	}
	return d.Value
}
