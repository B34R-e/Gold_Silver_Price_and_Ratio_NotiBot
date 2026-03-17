package fetcher

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"strings"
	"sync"
	"time"

	"github.com/gorilla/websocket"
	"github.com/user/notibot/models"
)

// PriceFetcher handles receiving prices from Binance WS and Yahoo Finance REST
type PriceFetcher struct {
	onPriceUpdate  func(models.PriceData)
	running        bool
	goldPrice      float64
	silverPrice    float64
	oilPrice       float64
	mu             sync.Mutex
	yahooPollSpeed time.Duration
}

const (
	binanceWSURL = "wss://fstream.binance.com/ws/xauusdt@ticker/xagusdt@ticker"
)

// NewPriceFetcher initializes the fetcher component
func NewPriceFetcher(updateCallback func(models.PriceData)) *PriceFetcher {
	return &PriceFetcher{
		onPriceUpdate:  updateCallback,
		yahooPollSpeed: 30 * time.Second,
	}
}

// Start spawns goroutines to fetch prices
func (f *PriceFetcher) Start() {
	f.running = true
	go f.binanceWSLoop()
	go f.oilPollingLoop()
}

// Stop cleanly stops the fetching loop
func (f *PriceFetcher) Stop() {
	f.running = false
}

// Binance WebSocket connection for Gold & Silver
func (f *PriceFetcher) binanceWSLoop() {
	log.Println("Connecting to Binance Futures WebSocket...")

	for f.running {
		c, _, err := websocket.DefaultDialer.Dial(binanceWSURL, nil)
		if err != nil {
			log.Printf("Binance WS Dial error: %v. Reconnecting in 5s...", err)
			time.Sleep(5 * time.Second)
			continue
		}
		log.Println("Binance WebSocket connected! Receiving Gold/Silver prices...")

		for f.running {
			_, message, err := c.ReadMessage()
			if err != nil {
				log.Printf("Binance WS Read error: %v. Reconnecting...", err)
				c.Close()
				break
			}
			f.handleBinanceTicker(message)
		}
		c.Close()
	}
}

// Oil price polling from Yahoo Finance (since Yahoo API is REST and simple enough)
func (f *PriceFetcher) oilPollingLoop() {
	log.Printf("Oil price polling started (every %v)", f.yahooPollSpeed)

	for f.running {
		price, err := f.fetchOilPrice()
		if err != nil {
			log.Printf("Oil polling error: %v", err)
		} else if price > 0 {
			f.mu.Lock()
			f.oilPrice = price
			f.mu.Unlock()
			// log.Printf("Oil price updated: $%.2f", price)
			f.emitPriceUpdate()
		}
		time.Sleep(f.yahooPollSpeed)
	}
}

type yahooQuoteResponse struct {
	QuoteResponse struct {
		Result []struct {
			RegularMarketPrice float64 `json:"regularMarketPrice"`
		} `json:"result"`
	} `json:"quoteResponse"`
}

func (f *PriceFetcher) fetchOilPrice() (float64, error) {
	// Yahoo Finance V7 API for quotes
	url := "https://query1.finance.yahoo.com/v7/finance/quote?symbols=CL=F"
	
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return 0, err
	}
	// Needed a user-agent to avoid 403 Forbidden with Yahoo Finance API sometimes.
	req.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)")

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return 0, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return 0, fmt.Errorf("unexpected status code: %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return 0, err
	}

	var data yahooQuoteResponse
	if err := json.Unmarshal(body, &data); err != nil {
		return 0, err
	}

	if len(data.QuoteResponse.Result) > 0 {
		return data.QuoteResponse.Result[0].RegularMarketPrice, nil
	}
	return 0, fmt.Errorf("no quote data returned")
}

// parse binance websocket JSON
func (f *PriceFetcher) handleBinanceTicker(msg []byte) {
	// Structure: {"e":"24hrTicker","s":"XAUUSDT","c":"2650.50",...}
	var data map[string]interface{}
	if err := json.Unmarshal(msg, &data); err != nil {
		// Ignore parse errors as it might be system messages or other payloads
		return
	}

	event, _ := data["e"].(string)
	if event != "24hrTicker" {
		return
	}

	symbolRaw, _ := data["s"].(string)
	symbol := strings.ToLower(symbolRaw)

	priceStr, _ := data["c"].(string)
	var price float64
	_, err := fmt.Sscanf(priceStr, "%f", &price)
	if err != nil || price <= 0 {
		return
	}

	f.mu.Lock()
	updated := false
	if symbol == "xauusdt" {
		f.goldPrice = price
		updated = true
	} else if symbol == "xagusdt" {
		f.silverPrice = price
		updated = true
	}
	f.mu.Unlock()

	if updated {
		f.emitPriceUpdate()
	}
}

// Calls callback when all three prices are populated
func (f *PriceFetcher) emitPriceUpdate() {
	f.mu.Lock()
	gold := f.goldPrice
	silver := f.silverPrice
	oil := f.oilPrice
	f.mu.Unlock()

	if gold > 0 && silver > 0 && oil > 0 {
		pd := models.PriceData{
			Oil:       oil,
			Gold:      gold,
			Silver:    silver,
			Timestamp: time.Now(),
		}
		pd.CalculateDerived()
		f.onPriceUpdate(pd)
	}
}
