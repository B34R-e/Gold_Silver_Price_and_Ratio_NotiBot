# 🥇 Gold/Silver Price & Ratio NotiBot

Bot tự động nhận giá vàng (XAUUSDT) và bạc (XAGUSDT) **realtime** từ Binance Futures WebSocket, tính **Gold/Silver Ratio**, gửi thông báo qua **Telegram + Discord** khi giá biến động.

---

## ✨ Tính năng

- **Giá realtime** — WebSocket từ Binance Futures (XAUUSDT + XAGUSDT), cập nhật mỗi giây
- **Gold/Silver Ratio** — tính tự động, làm tròn 1 chữ số thập phân
- **Thông báo thông minh** — chỉ gửi khi giá biến động ≥ X (default 0.25%), tự chống spam
- **Telegram Commands** — `/status`, `/delta`, `/help` — config trực tiếp từ Telegram
- **Heartbeat** — Bot tự báo "còn sống" mỗi 1 giờ
- **Config linh hoạt** — delta theo % hoặc số tuyệt đối, thay đổi qua Telegram hoặc file

---

## 📋 Yêu cầu

- Python 3.10+
- Telegram Bot Token
- Discord Webhook URL *(optional)*

---

## 🚀 Cài đặt

### 1. Clone và cài dependencies

```bash
git clone <repo-url>
cd Gold_Silver_Price_and_Ratio_NotiBot
pip install -r requirements.txt
```

### 2. Tạo Telegram Bot

1. Mở Telegram, tìm **@BotFather**
2. Gửi `/newbot`
3. Đặt tên bot (ví dụ: `Gold Silver NotiBot`)
4. Đặt username (ví dụ: `gs_notibot_bot`)
5. **Copy Bot Token** được cung cấp (dạng `123456:ABC-DEF...`)

**Tắt Group Privacy (bắt buộc):**
1. Trong **@BotFather**, gửi `/mybots`
2. Chọn bot vừa tạo
3. Chọn **Bot Settings** → **Group Privacy**
4. Chọn **Turn off**

> ⚠️ Nếu không tắt Group Privacy, bot sẽ **không nhận được tin nhắn** trong group → không lấy được Chat ID.

**Lấy Chat ID:**
1. Thêm bot vào group mà bạn muốn nhận thông báo
2. Gửi 1 tin nhắn bất kỳ trong group
3. Mở trình duyệt, truy cập:
   ```
   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
   ```
4. Tìm `"chat":{"id": -1234567890}` — đó là **Chat ID** của bạn (số âm = group)

### 3. Tạo Discord Webhook *(optional)*

1. Mở Discord, vào **server** muốn nhận thông báo
2. Click phải vào **channel** → **Edit Channel** (hoặc ⚙️)
3. Vào tab **Integrations** → **Webhooks**
4. Click **New Webhook**
5. Đặt tên (ví dụ: `Gold Silver Bot`)
6. Click **Copy Webhook URL**

### 4. Cấu hình

**Copy `.env.example` → `.env`:**

```bash
cp .env.example .env
```

**Mở `.env` và điền thông tin:**

```env
# Telegram
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_CHAT_ID=-1001234567890

# Discord
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/1234567890/abcdef...
```

**Tùy chỉnh `config.json` (nếu cần):**

```json
{
  "delta": {
    "gold": "0.25%",
    "silver": "0.25%"
  },
  "channels": ["telegram"]
}
```

> 💡 Muốn thêm Discord? Thêm `"discord"` vào channels: `["telegram", "discord"]` và điền Webhook URL trong `.env`.

| Config | Ý nghĩa | Ví dụ |
|---|---|---|
| `delta.gold` | Ngưỡng biến động vàng | `"0.25%"` hoặc `50` (USD) |
| `delta.silver` | Ngưỡng biến động bạc | `"0.25%"` hoặc `1` (USD) |
| `channels` | Kênh thông báo | `["telegram"]`, `["discord"]`, hoặc cả hai |

---

## ▶️ Chạy Bot

```bash
python -m src.main
```

Bot sẽ:
1. Kết nối Binance Futures WebSocket
2. Nhận giá XAUUSDT + XAGUSDT liên tục
3. Tính Gold/Silver Ratio
4. Gửi thông báo khi giá biến động ≥ ngưỡng

**Dừng bot:** `Ctrl + C`

---

## 📨 Mẫu thông báo

```
🥇 Vàng (XAU) ▲
━━━━━━━━━━━━━━━━━━
💰 Giá: $2,650.50
📊 Biến động: +6.75 (+0.26%)
📍 Giá trước: $2,643.75
⚖️ Gold/Silver Ratio: 84.2
🕐 14:30:15 01/03/2026
```

---

## 💬 Telegram Commands

| Command | Chức năng |
|---|---|
| `/status` | Xem giá hiện tại + config + uptime |
| `/delta` | Xem delta hiện tại |
| `/delta gold 0.5%` | Đặt delta vàng = 0.5% |
| `/delta silver 0.1` | Đặt delta bạc = $0.1 |
| `/help` | Danh sách commands |

> 💡 Thay đổi delta qua Telegram sẽ tự động lưu vào `config.json`.

---

## ❤️ Heartbeat

Bot tự gửi tin nhắn "Bot đang hoạt động" mỗi 1 giờ kèm giá hiện tại và số updates đã nhận.

---

## 🧪 Chạy Tests

```bash
python -m pytest tests/ -v
```

---

## 📁 Cấu trúc dự án

```
Gold_Silver_Price_and_Ratio_NotiBot/
├── src/
│   ├── main.py              # Entry point + command wiring
│   ├── config.py            # Config Manager (load + save)
│   ├── models.py            # PriceData, Alert
│   ├── price_fetcher.py     # Binance Futures WebSocket
│   ├── alert_engine.py      # Delta-based alert logic
│   ├── notifier.py          # Telegram + Discord adapters
│   └── telegram_commands.py # Telegram command listener
├── tests/
│   ├── test_config.py
│   └── test_alert_engine.py
├── docs/                    # Documentation
├── config.json              # User config
├── .env.example             # Secrets template
├── .env                     # Secrets (không commit)
├── requirements.txt
└── README.md
```

---

## ⚠️ Lưu ý

- **Không commit `.env`** — file này chứa tokens bí mật
- **Giá từ Binance Futures** — có thể lệch nhẹ so với giá vàng spot truyền thống, chấp nhận được cho mục đích thông báo
- **Bot hoạt động 24/7** — Binance Futures giao dịch liên tục
- **Khi restart** — giá hiện tại trở thành baseline mới (lastNotifiedPrice reset)
