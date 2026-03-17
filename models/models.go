package models

import (
	"fmt"
	"math"
	"time"
)

// PriceData represents parsed data from fetching services.
type PriceData struct {
	Oil             float64
	Gold            float64
	Silver          float64
	GoldSilverRatio float64
	OilXSilver      float64
	Timestamp       time.Time
}

// CalculateDerived computes the ratio and multiplication metrics.
func (p *PriceData) CalculateDerived() {
	if p.Silver > 0 {
		// Round to 1 decimal place
		p.GoldSilverRatio = math.Round((p.Gold/p.Silver)*10) / 10
	} else {
		p.GoldSilverRatio = 0.0
	}

	if p.Oil > 0 && p.Silver > 0 {
		// Round to 2 decimal places
		p.OilXSilver = math.Round((p.Oil*p.Silver)*100) / 100
	} else {
		p.OilXSilver = 0.0
	}
}

// SymbolInfo provides metadata for symbols.
type SymbolInfo struct {
	Emoji    string
	Name     string
	Decimals int
}

var SymbolMetadata = map[string]SymbolInfo{
	"oil":               {Emoji: "🛢️", Name: "Dầu (WTI)", Decimals: 2},
	"gold":              {Emoji: "🥇", Name: "Vàng (XAU)", Decimals: 2},
	"silver":            {Emoji: "🥈", Name: "Bạc (XAG)", Decimals: 4},
	"gold_silver_ratio": {Emoji: "⚖️", Name: "Gold/Silver Ratio", Decimals: 1},
	"oil_x_silver":      {Emoji: "📐", Name: "Oil × Silver", Decimals: 2},
}

// Alert represents an alert to be sent to users.
type Alert struct {
	Symbol            string
	CurrentPrice      float64
	LastNotifiedPrice float64
	Change            float64
	ChangePercent     float64
	Timestamp         time.Time
}

func (a *Alert) Direction() string {
	if a.Change > 0 {
		return "▲"
	}
	return "▼"
}

func (a *Alert) SymbolDisplay() string {
	info, ok := SymbolMetadata[a.Symbol]
	if !ok {
		return "📊 " + a.Symbol
	}
	return info.Emoji + " " + info.Name
}

func (a *Alert) FormatMessage() string {
	sign := ""
	if a.Change > 0 {
		sign = "+"
	}
	timeStr := a.Timestamp.Format("15:04:05 02/01/2006")

	decimals := 2
	if info, ok := SymbolMetadata[a.Symbol]; ok {
		decimals = info.Decimals
	}

	// Create format strings dynamically based on decimal requirements
	priceFmt := fmt.Sprintf("%%.,%df", decimals)
	if decimals == 1 {
		priceFmt = "%.1f"
	} else if decimals == 2 {
		priceFmt = "%.2f" // We will implement a comma formatter for real thousands separator if needed, for simplicity basic formatting first.
	} else if decimals == 4 {
		priceFmt = "%.4f"
	}

	currentPriceStr := formatNumber(a.CurrentPrice, priceFmt)
	changeStr := formatNumber(a.Change, priceFmt)
	lastPriceStr := formatNumber(a.LastNotifiedPrice, priceFmt)

	return fmt.Sprintf("%s %s\n"+
		"━━━━━━━━━━━━━━━━━━\n"+
		"💰 Giá: %s\n"+
		"📊 Biến động: %s%s (%s%.2f%%)\n"+
		"📍 Giá trước: %s\n"+
		"🕐 %s",
		a.SymbolDisplay(), a.Direction(),
		currentPriceStr,
		sign, changeStr, sign, a.ChangePercent,
		lastPriceStr,
		timeStr,
	)
}

// Helper func to format number with commas roughly. Go doesn't have a built-in one for floats that's trivial.
// We'll use a simple approximation string formatting or proper library if needed.
// For now, let's just use Sprintf and basic standard layout
func formatNumber(val float64, formatStr string) string {
	return fmt.Sprintf(formatStr, val)
}
