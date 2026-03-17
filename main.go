package main

import (
	"fmt"
	"log"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/user/notibot/alert"
	"github.com/user/notibot/config"
	"github.com/user/notibot/fetcher"
	"github.com/user/notibot/models"
	"github.com/user/notibot/notifier"
	"github.com/user/notibot/telegram"
)

type NotiBot struct {
	cfg         *config.Config
	alertEngine *alert.Engine
	dispatcher  *notifier.Dispatcher
	fetcher     *fetcher.PriceFetcher
	cmdListener *telegram.CommandListener

	priceCount  int
	startupSent bool
	latestPrice *models.PriceData
}

func main() {
	// Configure logging
	log.SetFlags(log.Ldate | log.Ltime | log.Lmicroseconds)

	log.Println(strings.Repeat("=", 50))
	log.Println("Oil/Gold/Silver NotiBot starting...")
	log.Println(strings.Repeat("=", 50))

	cfg, err := config.LoadConfig("config.json", ".env")
	if err != nil {
		log.Fatalf("Fatal: failed to load config: %v", err)
	}

	for _, sym := range config.AllSymbols {
		log.Printf("Delta %s: %+v", sym, cfg.Deltas[sym])
	}
	log.Printf("Channels: %v", cfg.Channels)

	bot := &NotiBot{
		cfg:         cfg,
		alertEngine: alert.NewEngine(cfg),
		dispatcher:  notifier.NewDispatcher(cfg),
		cmdListener: telegram.NewCommandListener(cfg.TelegramBotToken, cfg.TelegramChatID),
	}
	bot.fetcher = fetcher.NewPriceFetcher(bot.onPriceUpdate)

	bot.registerCommands()

	// Start modules
	bot.dispatcher.StartWorker()
	bot.fetcher.Start()
	bot.cmdListener.Start()

	// Startup sequence
	var deltaParts []string
	for _, sym := range config.AllSymbols {
		formatted := config.FormatDeltaToConfig(cfg.Deltas[sym])
		deltaParts = append(deltaParts, fmt.Sprintf("%s: %v", sym, formatted))
	}
	deltaSummary := strings.Join(deltaParts, ", ")

	startupMsg := fmt.Sprintf("🤖 Oil/Gold/Silver NotiBot đã khởi động!\n"+
		"📊 Delta: %s\n"+
		"📣 Channels: %s\n"+
		"💬 Commands: /status /delta /help", deltaSummary, strings.Join(cfg.Channels, ", "))
	
	bot.dispatcher.SendMessageSync(startupMsg)

	// Heartbeat loop & Stop signal handling
	go bot.heartbeatLoop()

	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
	
	<-sigChan
	log.Println("Shutting down...")
	bot.fetcher.Stop()
	bot.cmdListener.Stop()
	bot.dispatcher.SendMessageSync("🛑 Oil/Gold/Silver NotiBot đã dừng.")
	log.Println("Bot stopped.")
}

func (b *NotiBot) registerCommands() {
	b.cmdListener.Register("/status", b.cmdStatus)
	b.cmdListener.Register("/delta", b.cmdDelta)
	b.cmdListener.Register("/help", b.cmdHelp)
	log.Println("Telegram commands registered: /status, /delta, /help")
}

func (b *NotiBot) cmdStatus(args []string) {
	if b.latestPrice == nil {
		b.cmdListener.Reply("⏳ Chưa nhận được giá. Đợi vài giây...")
		return
	}

	p := b.latestPrice
	stats := b.dispatcher.Stats

	var deltaLines []string
	for _, sym := range config.AllSymbols {
		formatted := config.FormatDeltaToConfig(b.cfg.Deltas[sym])
		deltaLines = append(deltaLines, fmt.Sprintf("  %s: %v", sym, formatted))
	}
	deltaStr := strings.Join(deltaLines, "\n")
	
	timeStr := p.Timestamp.Format("15:04:05 02/01/2006")

	msg := fmt.Sprintf("📊 Trạng thái NotiBot\n"+
		"━━━━━━━━━━━━━━━━━━\n"+
		"🛢️ Dầu (WTI): $%.2f\n"+
		"🥇 Vàng (XAU): $%.2f\n"+
		"🥈 Bạc (XAG): $%.4f\n"+
		"⚖️ Gold/Silver Ratio: %.1f\n"+
		"📐 Oil × Silver: $%.2f\n"+
		"🕐 %s\n"+
		"━━━━━━━━━━━━━━━━━━\n"+
		"⚙️ Delta:\n%s\n"+
		"📡 %d updates | 📤 %d sent | ❌ %d failed | 📬 %d queued",
		p.Oil, p.Gold, p.Silver, p.GoldSilverRatio, p.OilXSilver,
		timeStr, deltaStr,
		b.priceCount, stats.Sent, stats.Failed, stats.Queued,
	)

	b.cmdListener.Reply(msg)
}

func (b *NotiBot) cmdDelta(args []string) {
	if len(args) == 0 {
		var lines []string
		for _, sym := range config.AllSymbols {
			info, ok := models.SymbolMetadata[sym]
			emoji := "📊"
			name := sym
			if ok {
				emoji = info.Emoji
				name = info.Name
			}
			formatted := config.FormatDeltaToConfig(b.cfg.Deltas[sym])
			lines = append(lines, fmt.Sprintf("%s %s: %v", emoji, name, formatted))
		}
		
		msg := "⚙️ Delta hiện tại:\n" + strings.Join(lines, "\n") + "\n\n" +
			"Cách dùng:\n" +
			"/delta oil 1%\n" +
			"/delta gold 0.5%\n" +
			"/delta silver 0.1\n" +
			"/delta gold_silver_ratio 0.5\n" +
			"/delta oil_x_silver 1%"
		
		b.cmdListener.Reply(msg)
		return
	}

	if len(args) < 2 {
		b.cmdListener.Reply(fmt.Sprintf("❌ Cú pháp: /delta <symbol> <giá trị>\nSymbols: %s", strings.Join(config.AllSymbols, ", ")))
		return
	}

	symbol := strings.ToLower(args[0])
	valueStr := args[1]

	validSymbol := false
	for _, s := range config.AllSymbols {
		if s == symbol {
			validSymbol = true
			break
		}
	}

	if !validSymbol {
		b.cmdListener.Reply(fmt.Sprintf("❌ Symbol phải là: %s", strings.Join(config.AllSymbols, ", ")))
		return
	}

	newDelta := config.ParseDelta(valueStr)
	b.cfg.Deltas[symbol] = newDelta
	if err := b.cfg.SaveToFile(); err != nil {
		log.Printf("Failed to save config: %v", err)
	}

	info, ok := models.SymbolMetadata[symbol]
	displayName := fmt.Sprintf("📊 %s", symbol)
	if ok {
		displayName = fmt.Sprintf("%s %s", info.Emoji, info.Name)
	}

	formatted := config.FormatDeltaToConfig(newDelta)
	b.cmdListener.Reply(fmt.Sprintf("✅ Đã cập nhật!\n%s: delta = %v", displayName, formatted))
	log.Printf("Delta %s updated via Telegram: %+v", symbol, newDelta)
}

func (b *NotiBot) cmdHelp(args []string) {
	msg := "📋 Commands:\n" +
		"━━━━━━━━━━━━━━━━━━\n" +
		"/status — Xem giá hiện tại + config\n" +
		"/delta — Xem delta hiện tại\n" +
		"/delta <symbol> <value> — Đặt delta\n" +
		"  Symbols: " + strings.Join(config.AllSymbols, ", ") + "\n" +
		"/help — Hiển thị help này"
	b.cmdListener.Reply(msg)
}

func (b *NotiBot) onPriceUpdate(data models.PriceData) {
	b.priceCount++
	b.latestPrice = &data

	if !b.startupSent {
		b.startupSent = true
		timeStr := data.Timestamp.Format("15:04:05 02/01/2006")
		
		msg := fmt.Sprintf("📊 Giá hiện tại:\n"+
			"━━━━━━━━━━━━━━━━━━\n"+
			"🛢️ Dầu (WTI): $%.2f\n"+
			"🥇 Vàng (XAU): $%.2f\n"+
			"🥈 Bạc (XAG): $%.4f\n"+
			"⚖️ Gold/Silver Ratio: %.1f\n"+
			"📐 Oil × Silver: $%.2f\n"+
			"🕐 %s",
			data.Oil, data.Gold, data.Silver, data.GoldSilverRatio, data.OilXSilver, timeStr)
		
		b.dispatcher.SendMessage(msg)
	}

	if b.priceCount%10 == 0 {
		log.Printf("[#%d] OIL: $%.2f | XAU: $%.2f | XAG: $%.4f | G/S: %.1f | O×S: $%.2f",
			b.priceCount, data.Oil, data.Gold, data.Silver, data.GoldSilverRatio, data.OilXSilver)
	}

	alerts := b.alertEngine.Check(data)
	for _, a := range alerts {
		b.dispatcher.SendAlert(a)
	}
}

func (b *NotiBot) heartbeatLoop() {
	log.Println("Heartbeat started (every 1 hour)")
	for {
		time.Sleep(1 * time.Hour)
		now := time.Now().Format("15:04:05 02/01/2006")
		priceInfo := ""
		if b.latestPrice != nil {
			p := b.latestPrice
			priceInfo = fmt.Sprintf("\n🛢️ OIL: $%.2f | 🥇 XAU: $%.2f | 🥈 XAG: $%.4f\n"+
				"⚖️ G/S: %.1f | 📐 O×S: $%.2f", p.Oil, p.Gold, p.Silver, p.GoldSilverRatio, p.OilXSilver)
		}
		msg := fmt.Sprintf("❤️ Bot đang hoạt động%s\n📡 %d updates | 🕐 %s", priceInfo, b.priceCount, now)
		b.dispatcher.SendMessage(msg)
		log.Printf("Heartbeat sent (%d updates)", b.priceCount)
	}
}
