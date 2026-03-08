# 求職 12 週 Discord Bot · 完整架構文件

## 📁 專案結構

```
discord-job-bot/
├── bot/
│   ├── bot.py              # Discord Bot 主程式
│   ├── requirements.txt    # Python 依賴
│   └── .env               # 環境變數（不要 commit！）
│
├── dashboard/              # Next.js Dashboard
│   ├── app/
│   │   ├── page.tsx        # 首頁：無參數為說明；?discord_id=xxx 為成員專屬頁
│   │   ├── admin/page.tsx  # 管理員後台（/admin，需輸入密碼）
│   │   └── api/            # stats, member, insights, admin/session
│   ├── package.json
│   └── .env.local
│
└── supabase/
    └── schema.sql          # 資料庫建表 SQL
```

---

## 🚀 Step-by-Step 部署指南

### Step 1：建立 Supabase 資料庫（免費）

1. 到 https://supabase.com 建立免費帳號
2. 新建 Project
3. 進入 **SQL Editor**，貼上 `schema.sql` 全部內容，執行
4. 進入 **Settings > API**，複製：
   - `Project URL` → `SUPABASE_URL`
   - `service_role` key → `SUPABASE_KEY`（Bot 用，勿公開）
   - `anon` key → `NEXT_PUBLIC_SUPABASE_ANON_KEY`（Dashboard 用）

### Step 2：建立 Discord Bot

1. 到 https://discord.com/developers/applications
2. 新建 Application → Bot
3. 開啟 **Message Content Intent**（必要！）
4. 複製 Token → `DISCORD_TOKEN`
5. 用以下連結邀請 Bot 到你的伺服器：
   ```
   https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=274877909056&scope=bot
   ```

### Step 3：部署 Discord Bot

**本地測試：**
```bash
cd bot/
pip install -r requirements.txt
cp .env.example .env   # 填入你的 key
python bot.py
```

**正式部署（Railway，免費方案可用）：**
1. 到 https://railway.app
2. New Project → Deploy from GitHub
3. 在 Variables 填入所有環境變數
4. 選 Python 環境，設定 Start Command: `python bot/bot.py`

### Step 4：部署 Dashboard

```bash
cd dashboard/
npm install
cp .env.example .env.local   # 填入 key
npm run dev    # 本地測試
```

**正式部署（Vercel，免費）：**
```bash
npx vercel --prod
```
在 Vercel Dashboard 填入環境變數即可。

---

## ⚙️ 環境變數

### bot/.env
```env
DISCORD_TOKEN=你的_discord_bot_token
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=你的_service_role_key（不能公開！）
GEMINI_API_KEY=你的_gemini_api_key
DASHBOARD_URL=https://你的-dashboard.vercel.app
```

> `DASHBOARD_URL` 為選填；有設定時，成員可用 `!me` 取得個人連結，格式為 `https://你的網域/?discord_id=使用者ID`。

### dashboard/.env.local
```env
NEXT_PUBLIC_SUPABASE_URL=https://xxxxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=你的_anon_key（這個可以公開）
SUPABASE_SERVICE_KEY=你的_service_role_key（Server-side 用）
GEMINI_API_KEY=你的_gemini_api_key
ADMIN_PASSWORD=隨機一組管理員密碼（保護 /admin）
```

> **ADMIN_PASSWORD**：必填（若要用 /admin）。保護管理員後台，僅你知道即可。
>
> **GEMINI_API_KEY**：選填。有設定時，Dashboard「AI 洞察」分頁會呼叫 Gemini 產出分析；未設定時該分頁會顯示設定說明。可與 Bot 使用同一把 key。
>
> **若 Dashboard 今日/本週一直顯示 0**：請到 Supabase Dashboard > SQL Editor 執行一次 `supabase/migrations/001_fix_dashboard_timezone.sql`。該 migration 會讓「今日打卡」與「本週」改為**每位成員的當地日期**（美東成員用美東的今天/本週、台灣成員用台灣的今天/本週），所以美東 3/8 晚上打卡會顯示在 3/8，不會被算成台灣的 3/9。

---

## 🤖 Bot 指令列表

| 指令 | 說明 |
|------|------|
| （直接在打卡頻道發任何訊息） | 自動打卡 + AI 回覆 |
| `!stats` | 查看自己的打卡統計 |
| `!stats @成員` | 查看指定成員統計 |
| `!leaderboard` 或 `!lb` | 本週打卡排行榜 |
| `!me` 或 `!dashboard` | 取得個人 Dashboard 連結（Bot 私訊專屬連結 `/?discord_id=你的ID`，僅能看到自己的打卡） |

---

## 💰 費用估算

| 服務 | 免費額度 | 預估用量 |
|------|---------|---------|
| Supabase | 500MB 資料庫、50,000 請求/月 | ✅ 綽綽有餘 |
| Railway (Bot) | $5 credits/月 | ✅ 足夠小型 Bot |
| Vercel (Dashboard) | 無限靜態、100GB 流量 | ✅ 免費 |
| Gemini API | 按用量計費 | ~$0.5-2/月（20人群組）|

**總費用：基本免費，Gemini API 約 $1-2 美金/月**

---

## 🔮 未來 AI 功能擴充

- [ ] **求職建議**：成員輸入 `!advice` 獲得個人化求職策略
- [ ] **履歷 review**：貼上履歷片段，AI 給出優化建議
- [ ] **面試 Q&A**：模擬面試對話練習
- [ ] **週報 Email**：自動寄送個人化週報給每個成員
- [ ] **情緒預警**：連續 3 天情緒低落，自動通知管理員

---

## 🧪 本地測試 Bot

測試打卡是否正常儲存：
```python
# 在 Python shell 中
import asyncio
from bot import save_checkin, get_or_create_member

# 模擬成員
member = get_or_create_member("123456789", "testuser", "測試用戶")
checkin = save_checkin(member["id"], "今天測試一下！", "channel_id", "message_id")
print(checkin)
```
