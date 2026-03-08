# 求職 12 週 · 部署檢查清單

部署前可依序打勾，確保不遺漏。Supabase / Railway / Vercel 可依你實際順序調整。

---

## 一、Supabase 資料庫

- [ ] 已註冊並建立 Project（https://supabase.com）
- [ ] 在 **SQL Editor** 執行過 `supabase/schema.sql`（或所有 migrations）
- [ ] 已執行 `supabase/migrations/001_fix_dashboard_timezone.sql`（讓「今日/本週」依成員時區正確顯示）
- [ ] 已複製並妥善保存：
  - [ ] **Project URL** → 用於 `SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_URL`
  - [ ] **service_role key** → 用於 `SUPABASE_KEY`（Bot）與 `SUPABASE_SERVICE_KEY`（Dashboard，若使用）
  - [ ] **anon key** → 用於 `NEXT_PUBLIC_SUPABASE_ANON_KEY`（Dashboard）

---

## 二、Discord Bot（本機與開發）

- [ ] 已在 https://discord.com/developers/applications 建立 Application 與 Bot
- [ ] Bot 已開啟 **Message Content Intent**（Privileged Gateway Intents）
- [ ] 已複製 **Bot Token** → `DISCORD_TOKEN`
- [ ] 已用邀請連結把 Bot 加入目標伺服器（替換 `YOUR_CLIENT_ID`）：
  ```
  https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=274877909056&scope=bot
  ```
- [X] 本機 `bot/.env` 已設定並可正常跑 `python bot.py`（可選，建議先驗證）

---

## 三、Railway 部署 Bot

- [ ] 程式碼已 push 到 GitHub（Railway 從 GitHub 部署）
- [ ] 到 https://railway.app 登入，**New Project** → **Deploy from GitHub** → 選擇本專案 repo
- [ ] 在 Service **Settings** 設定 **Root Directory** = `bot`
- [ ] 在 **Settings** 設定 **Start Command** = `python bot.py`
- [ ] 在 **Variables** 新增所有必要變數：

  | 變數 | 必填 | 說明 |
  |------|------|------|
  | `DISCORD_TOKEN` | ✅ | Discord Bot Token |
  | `SUPABASE_URL` | ✅ | Supabase Project URL |
  | `SUPABASE_KEY` | ✅ | Supabase **service_role** key（勿公開） |
  | `GEMINI_API_KEY` | ✅ | Gemini API key（Bot AI 回覆用） |
  | `DASHBOARD_URL` | 選填 | Dashboard 正式網址（設好後 `!me` 會回正確連結） |

- [ ] 部署完成後在 **Deployments → Logs** 確認無錯誤、Bot 已上線（例如看到 `on_ready` 或登入成功訊息）
- [ ] 到 Discord 打卡頻道發一則訊息，確認 Bot 有回覆、有寫入 Supabase

---

## 四、Dashboard 部署（Vercel）

- [ ] 本機在 `dashboard/` 已跑過 `npm install` 且 `npm run dev` 可正常開啟
- [ ] 在專案根目錄執行：`cd dashboard && npx vercel --prod`（或從 Vercel 連 GitHub 選 `dashboard` 為 Root Directory）
- [ ] 若用 Vercel 連 GitHub：在專案設定中 **Root Directory** 設為 `dashboard`
- [ ] 在 Vercel 專案 **Settings → Environment Variables** 新增：

  | 變數 | 必填 | 說明 |
  |------|------|------|
  | `NEXT_PUBLIC_SUPABASE_URL` | ✅ | Supabase Project URL |
  | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | ✅ | Supabase **anon** key（可公開） |
  | `SUPABASE_SERVICE_KEY` | 選填 | Supabase **service_role**（若 API 需更高權限） |
  | `GEMINI_API_KEY` | 選填 | 「AI 洞察」分頁用；可與 Bot 共用同一把 |
  | `ADMIN_PASSWORD` | ✅ 若用 /admin | 管理員後台密碼（自訂一組，勿與他處共用） |

- [ ] 部署完成後開啟 Production URL，確認：
  - [ ] 首頁可開啟（或說明頁正常）
  - [ ] `/api/stats` 有回傳資料（可瀏覽 `https://你的網域.vercel.app/api/stats`）
  - [ ] 若有設 `?discord_id=某成員ID`，成員頁可顯示資料
  - [ ] `/admin` 輸入密碼可進入管理員後台

---

## 五、串接 Bot 與 Dashboard

- [ ] 將 Dashboard 正式網址（例如 `https://xxx.vercel.app`）填回 Railway 的 **Variables** → `DASHBOARD_URL`
- [ ] Railway 重新部署一次（或等自動部署），讓 Bot 讀到新 `DASHBOARD_URL`
- [ ] 在 Discord 用 `!me` 或 `!dashboard` 測試，確認回覆的連結可開啟並顯示自己的打卡

---

## 六、上線後快速驗證

- [ ] Discord 打卡頻道：發訊息 → Bot 有回覆、Supabase `checkins` / `ai_replies` 有資料
- [ ] Dashboard 首頁或 stats：今日/本週數字會更新（可等 30 秒輪詢或手動重整）
- [ ] `/admin`：可登入、可看到資料與 AI 洞察（若已設 `GEMINI_API_KEY`）
- [ ] `!me` 連結：點開後為該成員的個人頁，資料正確

---

## 備註

- **時區**：若「今日打卡」或「本週」顯示不對，請再確認已執行 `supabase/migrations/001_fix_dashboard_timezone.sql`。
- **Bot 重啟**：Railway 免費方案可能有 sleep；若 Bot 常離線，可查 Railway 用量或考慮付費方案。
- **密鑰安全**：`DISCORD_TOKEN`、`SUPABASE_KEY`、`SUPABASE_SERVICE_KEY`、`ADMIN_PASSWORD` 切勿 commit 或貼到公開處。
