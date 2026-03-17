package alert

import (
	"log"
	"math"

	"github.com/user/notibot/config"
	"github.com/user/notibot/models"
)

// Engine compares current price with the last notified price
// If change >= delta, generates an Alert and updates baseline.
type Engine struct {
	cfg          *config.Config
	lastNotified map[string]float64
}

// NewEngine creates an alert engine instance
func NewEngine(cfg *config.Config) *Engine {
	e := &Engine{
		cfg:          cfg,
		lastNotified: make(map[string]float64),
	}
	for _, sym := range config.AllSymbols {
		e.lastNotified[sym] = 0.0 // 0 means no baseline yet
	}
	return e
}

// getPrice returns the value of the symbol from PriceData struct safely.
func getPrice(symbol string, data models.PriceData) float64 {
	switch symbol {
	case "oil":
		return data.Oil
	case "gold":
		return data.Gold
	case "silver":
		return data.Silver
	case "gold_silver_ratio":
		return data.GoldSilverRatio
	case "oil_x_silver":
		return data.OilXSilver
	}
	return 0.0
}

// Check evaluates all symbols and returns a slice of generated alerts
func (e *Engine) Check(data models.PriceData) []models.Alert {
	var alerts []models.Alert

	for _, symbol := range config.AllSymbols {
		currentPrice := getPrice(symbol, data)
		if currentPrice <= 0 {
			continue
		}

		lastPrice := e.lastNotified[symbol]

		// First time seeing this price -> set baseline, do not alert
		if lastPrice == 0.0 {
			e.lastNotified[symbol] = currentPrice
			log.Printf("%s baseline set: %.2f", symbol, currentPrice)
			continue
		}

		alert := e.checkSymbol(symbol, currentPrice, lastPrice, data)
		if alert != nil {
			e.lastNotified[symbol] = currentPrice
			alerts = append(alerts, *alert)
		}
	}

	return alerts
}

func (e *Engine) checkSymbol(symbol string, current, last float64, data models.PriceData) *models.Alert {
	if last <= 0 {
		return nil
	}

	change := current - last
	changeAbs := math.Abs(change)
	changePercent := (change / last) * 100.0

	threshold := e.cfg.GetDeltaThreshold(symbol, last)

	if changeAbs >= threshold {
		alert := &models.Alert{
			Symbol:            symbol,
			CurrentPrice:      current,
			LastNotifiedPrice: last,
			Change:            change,
			ChangePercent:     changePercent,
			GoldSilverRatio:   data.GoldSilverRatio,
			OilXSilver:        data.OilXSilver,
			Timestamp:         data.Timestamp,
		}
		log.Printf("ALERT: %s changed %+.2f (%+.2f%%) from %.2f to %.2f",
			symbol, change, changePercent, last, current)
		return alert
	}

	return nil
}
