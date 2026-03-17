package notifier

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/user/notibot/config"
	"github.com/user/notibot/models"
)

// ChannelAdapter interface for Telegram and Discord
type ChannelAdapter interface {
	Send(message string) bool
	Name() string
}

// TelegramAdapter implementation
type TelegramAdapter struct {
	botToken string
	chatID   string
}

func (t *TelegramAdapter) Name() string { return "Telegram" }
func (t *TelegramAdapter) Send(message string) bool {
	if t.botToken == "" || t.chatID == "" {
		log.Println("Telegram: bot_token or chat_id not configured, skipping")
		return false
	}

	url := fmt.Sprintf("https://api.telegram.org/bot%s/sendMessage", t.botToken)
	payload := map[string]string{
		"chat_id":    t.chatID,
		"text":       message,
		// No parse_mode by default so we don't need to escape < > &
		"parse_mode": "HTML",
	}

	for key, val := range payload {
		if key == "text" {
			// Minimal escaping to prevent telegram api from rejecting the message
			val = strings.ReplaceAll(val, "&", "&amp;")
			val = strings.ReplaceAll(val, "<", "&lt;")
			val = strings.ReplaceAll(val, ">", "&gt;")
			payload[key] = val
		}
	}


	jsonBody, _ := json.Marshal(payload)
	resp, err := http.Post(url, "application/json", bytes.NewBuffer(jsonBody))
	if err != nil {
		log.Printf("Telegram POST error: %v", err)
		return false
	}
	defer resp.Body.Close()

	if resp.StatusCode == 200 {
		return true
	} else if resp.StatusCode == 429 {
		// Rate limit
		var result map[string]interface{}
		json.NewDecoder(resp.Body).Decode(&result)
		retryAfter := float64(5) // default 5s
		if parameters, ok := result["parameters"].(map[string]interface{}); ok {
			if rValue, ok := parameters["retry_after"].(float64); ok {
				retryAfter = rValue
			}
		}
		log.Printf("Telegram rate limited, retrying after %.0fs", retryAfter)
		time.Sleep(time.Duration(retryAfter) * time.Second)
		// Retry once simply by making request again inline
		respRetry, errRetry := http.Post(url, "application/json", bytes.NewBuffer(jsonBody))
		if errRetry == nil && respRetry.StatusCode == 200 {
			respRetry.Body.Close()
			return true
		}
		if respRetry != nil {
			respRetry.Body.Close()
		}
		return false
	}

	var errorData map[string]interface{}
	json.NewDecoder(resp.Body).Decode(&errorData)
	log.Printf("Telegram error %d: %v", resp.StatusCode, errorData)
	return false
}

// DiscordAdapter implementation
type DiscordAdapter struct {
	webhookURL string
}

func (d *DiscordAdapter) Name() string { return "Discord" }
func (d *DiscordAdapter) Send(message string) bool {
	if d.webhookURL == "" {
		log.Println("Discord: webhook_url not configured, skipping")
		return false
	}

	payload := map[string]string{"content": message}
	jsonBody, _ := json.Marshal(payload)

	resp, err := http.Post(d.webhookURL, "application/json", bytes.NewBuffer(jsonBody))
	if err != nil {
		log.Printf("Discord POST error: %v", err)
		return false
	}
	defer resp.Body.Close()

	if resp.StatusCode == 200 || resp.StatusCode == 204 {
		return true
	}
	log.Printf("Discord error %d", resp.StatusCode)
	return false
}

// Stats tracking sent/failed notifications
type Stats struct {
	Sent   int
	Failed int
	Queued int
}

// Dispatcher coordinates sending messages through configured channels in background
type Dispatcher struct {
	cfg      *config.Config
	adapters []ChannelAdapter
	queue    chan string
	Stats    Stats
}

// NewDispatcher creates the notification dispatcher
func NewDispatcher(cfg *config.Config) *Dispatcher {
	d := &Dispatcher{
		cfg:   cfg,
		queue: make(chan string, 1000), // buffered channel for messages
	}

	for _, ch := range cfg.Channels {
		if ch == "telegram" {
			d.adapters = append(d.adapters, &TelegramAdapter{botToken: cfg.TelegramBotToken, chatID: cfg.TelegramChatID})
			log.Println("Telegram adapter initialized")
		} else if ch == "discord" {
			d.adapters = append(d.adapters, &DiscordAdapter{webhookURL: cfg.DiscordWebhookURL})
			log.Println("Discord adapter initialized")
		}
	}

	return d
}

// StartWorker initiates the background goroutine to process the queue
func (d *Dispatcher) StartWorker() {
	go func() {
		log.Println("Notification worker started (background goroutine)")
		for msg := range d.queue {
			d.Stats.Queued--
			for _, adapter := range d.adapters {
				success := adapter.Send(msg)
				if success {
					d.Stats.Sent++
				} else {
					log.Printf("Failed to send via %s. Retrying...", adapter.Name())
					// Retry 1x inline
					if adapter.Send(msg) {
						d.Stats.Sent++
					} else {
						d.Stats.Failed++
						log.Printf("Failed to send via %s after retry.", adapter.Name())
					}
				}
			}
		}
	}()
}

func (d *Dispatcher) SendAlert(alert models.Alert) {
	d.SendMessage(alert.FormatMessage())
}

// SendMessage adds a message to the channel
func (d *Dispatcher) SendMessage(message string) {
	d.Stats.Queued++
	select {
	case d.queue <- message:
		// added successfully
	default:
		log.Println("Warning: Notification queue is full, dropping message.")
		d.Stats.Queued--
		d.Stats.Failed++
	}
}

// SendMessageSync sends a message directly, blocking execution (mostly used on startup/shutdown)
func (d *Dispatcher) SendMessageSync(message string) {
	for _, adapter := range d.adapters {
		adapter.Send(message)
	}
}
