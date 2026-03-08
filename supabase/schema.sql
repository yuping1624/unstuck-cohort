-- =============================================
-- 求職群組 Discord Bot · Supabase Schema
-- 整合版：包含時區支援、原子習慣設計
-- 在 Supabase Dashboard > SQL Editor 貼上全部執行
-- =============================================


-- ─────────────────────────────────────────
-- 成員表
-- ─────────────────────────────────────────
CREATE TABLE members (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  discord_id        TEXT UNIQUE NOT NULL,   -- Discord 數字 ID
  username          TEXT NOT NULL,           -- Discord 帳號名
  display_name      TEXT NOT NULL,           -- 群組顯示名稱
  timezone          TEXT NOT NULL DEFAULT 'Asia/Taipei',  -- 成員所在時區
  current_streak    INT DEFAULT 0,           -- 目前連續打卡天數
  longest_streak    INT DEFAULT 0,           -- 歷史最長連續天數
  last_checkin_date DATE,                    -- 最後打卡日期（用成員本地時間）
  joined_at         TIMESTAMPTZ DEFAULT NOW(),
  created_at        TIMESTAMPTZ DEFAULT NOW()
);


-- ─────────────────────────────────────────
-- 打卡表
-- content 完全自由，一句話就好，Bot 不強制格式
-- ─────────────────────────────────────────
CREATE TABLE checkins (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  member_id    UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
  content      TEXT NOT NULL,
  date         DATE NOT NULL,              -- 用成員本地時間的日期（Bot 負責換算）
  week_number  INT NOT NULL,               -- 第幾週（1-12）
  channel_id   TEXT,
  message_id   TEXT,
  created_at   TIMESTAMPTZ DEFAULT NOW(),  -- 實際發訊息的 UTC 時間
  UNIQUE(member_id, date)                  -- 每人每天只能一筆，重複自動忽略
);


-- ─────────────────────────────────────────
-- AI 回覆表
-- ─────────────────────────────────────────
CREATE TABLE ai_replies (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  checkin_id  UUID NOT NULL REFERENCES checkins(id) ON DELETE CASCADE,
  reply       TEXT NOT NULL,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);


-- ─────────────────────────────────────────
-- 索引（讓查詢更快）
-- ─────────────────────────────────────────
CREATE INDEX idx_checkins_date     ON checkins(date);
CREATE INDEX idx_checkins_member   ON checkins(member_id);
CREATE INDEX idx_checkins_week     ON checkins(week_number);
CREATE INDEX idx_members_discord   ON members(discord_id);


-- =============================================
-- 週排行榜 Function（Bot !leaderboard 指令用）
-- 依「活動第 N 週」：week_start <= date < week_end
-- =============================================
CREATE OR REPLACE FUNCTION weekly_leaderboard(week_start DATE, week_end DATE)
RETURNS TABLE (
  display_name  TEXT,
  discord_id    TEXT,
  checkin_count BIGINT
) LANGUAGE SQL AS $$
  SELECT
    m.display_name,
    m.discord_id,
    COUNT(c.id) AS checkin_count
  FROM members m
  LEFT JOIN checkins c
    ON c.member_id = m.id
    AND c.date >= week_start
    AND c.date < week_end
  GROUP BY m.id, m.display_name, m.discord_id
  HAVING COUNT(c.id) > 0
  ORDER BY checkin_count DESC
  LIMIT 20;
$$;


-- =============================================
-- Dashboard Views
-- =============================================

-- 今日打卡總覽（含 AI 回覆）
-- 用「該成員當地今天」：c.date = 成員時區的今天，所以美東 3/8 晚上打卡會顯示在 3/8，不會算成台灣的 3/9
CREATE OR REPLACE VIEW today_checkins AS
SELECT DISTINCT ON (c.id)
  c.id,
  c.content,
  c.date,
  c.created_at,
  c.week_number,
  m.display_name,
  m.discord_id,
  m.current_streak,
  m.timezone,
  ar.reply AS ai_reply
FROM checkins c
JOIN members m ON m.id = c.member_id
LEFT JOIN ai_replies ar ON ar.checkin_id = c.id
WHERE c.date = (NOW() AT TIME ZONE COALESCE(m.timezone, 'Asia/Taipei'))::date
ORDER BY c.id, ar.created_at DESC;

-- 每日打卡人數（過去 30 天，Dashboard 圖表用）
CREATE OR REPLACE VIEW daily_stats AS
SELECT
  date,
  COUNT(DISTINCT member_id) AS checkin_count
FROM checkins
WHERE date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY date
ORDER BY date;

-- 成員總覽（含本週 + 累計打卡數，Dashboard 成員列表用）
-- 本週＝該成員當地「本週一～日」內的打卡數（美東用美東的週、台灣用台灣的週）
CREATE OR REPLACE VIEW member_overview AS
SELECT
  m.*,
  COUNT(c.id) AS total_checkins,
  COUNT(c.id) FILTER (
    WHERE c.date >= (
      (NOW() AT TIME ZONE COALESCE(m.timezone, 'Asia/Taipei'))::date
      - ((EXTRACT(DOW FROM (NOW() AT TIME ZONE COALESCE(m.timezone, 'Asia/Taipei')))::int + 6) % 7)
    )
    AND c.date <= (
      (NOW() AT TIME ZONE COALESCE(m.timezone, 'Asia/Taipei'))::date
      - ((EXTRACT(DOW FROM (NOW() AT TIME ZONE COALESCE(m.timezone, 'Asia/Taipei')))::int + 6) % 7)
      + 6
    )
  ) AS this_week_checkins
FROM members m
LEFT JOIN checkins c ON c.member_id = m.id
GROUP BY m.id
ORDER BY m.current_streak DESC;


-- =============================================
-- Row Level Security
-- anon key（Dashboard）只能讀
-- service_role key（Bot）不受限制，可以寫入
-- =============================================
ALTER TABLE members    ENABLE ROW LEVEL SECURITY;
ALTER TABLE checkins   ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_replies ENABLE ROW LEVEL SECURITY;

CREATE POLICY "allow_read" ON members    FOR SELECT USING (true);
CREATE POLICY "allow_read" ON checkins   FOR SELECT USING (true);
CREATE POLICY "allow_read" ON ai_replies FOR SELECT USING (true);


-- =============================================
-- 手動新增成員資料（填好再執行）
-- 怎麼找 Discord ID：
--   Discord 設定 → 進階 → 開啟「開發者模式」
--   對著成員頭像右鍵 → 複製使用者 ID
-- =============================================
INSERT INTO members (discord_id, username, display_name, timezone) VALUES
-- 台灣成員（4人）
('填入Discord數字ID', '填入username', '填入顯示名稱', 'Asia/Taipei'),
('填入Discord數字ID', '填入username', '填入顯示名稱', 'Asia/Taipei'),
('填入Discord數字ID', '填入username', '填入顯示名稱', 'Asia/Taipei'),
('填入Discord數字ID', '填入username', '填入顯示名稱', 'Asia/Taipei'),
-- 加拿大 + 美國東岸（3人）
('填入Discord數字ID', '填入username', '填入顯示名稱', 'America/Toronto'),
('填入Discord數字ID', '填入username', '填入顯示名稱', 'America/Toronto'),
('填入Discord數字ID', '填入username', '填入顯示名稱', 'America/Toronto');