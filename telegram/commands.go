package telegram

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"strconv"
	"strings"
	"time"
)

// CommandHandler is a function type for handling telegram bot commands
type CommandHandler func(args []string)

// CommandListener polls telegram for updates
type CommandListener struct {
	botToken string
	chatID   string
	baseURL  string
	offset   int
	handlers map[string]CommandHandler
	running  bool
}

func NewCommandListener(token, chatID string) *CommandListener {
	return &CommandListener{
		botToken: token,
		chatID:   chatID,
		baseURL:  fmt.Sprintf("https://api.telegram.org/bot%s", token),
		handlers: make(map[string]CommandHandler),
	}
}

func (l *CommandListener) Register(cmd string, handler CommandHandler) {
	l.handlers[cmd] = handler
}

func (l *CommandListener) Start() {
	l.running = true
	log.Println("Telegram command listener started")
	go l.pollLoop()
}

func (l *CommandListener) Stop() {
	l.running = false
}

func (l *CommandListener) pollLoop() {
	for l.running {
		updates := l.pollOnce()
		if len(updates) > 0 {
			l.processUpdates(updates)
		}
		time.Sleep(1 * time.Second)
	}
}

func (l *CommandListener) pollOnce() []map[string]interface{} {
	url := fmt.Sprintf("%s/getUpdates?offset=%d&timeout=2&allowed_updates=[\"message\"]", l.baseURL, l.offset)
	
	client := http.Client{Timeout: 10 * time.Second}
	resp, err := client.Get(url)
	if err != nil {
		// log.Printf("Telegram getUpdates error: %v", err)
		return nil
	}
	defer resp.Body.Close()

	if resp.StatusCode != 200 {
		return nil
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil
	}

	var data map[string]interface{}
	if err := json.Unmarshal(body, &data); err != nil {
		return nil
	}

	if okVal, ok := data["ok"].(bool); !ok || !okVal {
		return nil
	}

	resultsRaw, ok := data["result"].([]interface{})
	if !ok || len(resultsRaw) == 0 {
		return nil
	}

	var updates []map[string]interface{}
	for _, r := range resultsRaw {
		if updateMap, ok := r.(map[string]interface{}); ok {
			updates = append(updates, updateMap)
			if updateID, ok := updateMap["update_id"].(float64); ok {
				l.offset = int(updateID) + 1
			}
		}
	}
	return updates
}

func (l *CommandListener) processUpdates(updates []map[string]interface{}) {
	for _, update := range updates {
		msg, ok := update["message"].(map[string]interface{})
		if !ok {
			continue
		}

		textRaw, ok := msg["text"].(string)
		if !ok {
			continue
		}
		text := strings.TrimSpace(textRaw)

		chatMap, ok := msg["chat"].(map[string]interface{})
		if !ok {
			continue
		}
		
		var incomingChatID string
		// chat ID could be float or int depending on unmarshal
		if idFloat, ok := chatMap["id"].(float64); ok {
			incomingChatID = strconv.FormatInt(int64(idFloat), 10)
		} else if idInt, ok := chatMap["id"].(int); ok {
			incomingChatID = strconv.Itoa(idInt)
		}

		// Ensure it's the correct chat
		if incomingChatID != l.chatID {
			continue
		}

		if !strings.HasPrefix(text, "/") {
			continue
		}

		parts := strings.Fields(text)
		if len(parts) == 0 {
			continue
		}

		command := strings.ToLower(parts[0])
		command = strings.Split(command, "@")[0] // Handle /cmd@botname
		args := parts[1:]

		log.Printf("Command received: %s %v", command, args)

		if handler, exists := l.handlers[command]; exists {
			handler(args)
		} else {
			log.Printf("Unknown command: %s", command)
		}
	}
}

func (l *CommandListener) Reply(text string) {
	url := fmt.Sprintf("%s/sendMessage", l.baseURL)

	payload := map[string]string{
		"chat_id": l.chatID,
		"text":    text,
	}

	jsonBody, _ := json.Marshal(payload)
	resp, err := http.Post(url, "application/json", strings.NewReader(string(jsonBody)))
	if err != nil {
		log.Printf("Telegram reply error: %v", err)
		return
	}
	defer resp.Body.Close()
}
