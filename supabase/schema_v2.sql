-- =============================================
-- 求職群組 Discord Bot · Supabase Schema v2
-- 整合所有 migration（001-004）
-- 在 Supabase Dashboard > SQL Editor 貼上全部執行
-- =============================================

-- ─────────────────────────────────────────
-- 成員表
-- ─────────────────────────────────────────
CREATE TABLE members (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  discord_id            TEXT UNIQUE NOT NULL,
  username              TEXT NOT NULL,
  display_name          TEXT NOT NULL,
  timezone              TEXT NOT NULL DEFAULT 'Asia/Taipei',
  current_streak        INT DEFAULT 0,
  longest_streak        INT DEFAULT 0,
  last_checkin_date     DATE,
  goal_12week_summary   TEXT,
  goal_thread_current   TEXT,
  goal_thread_history   TEXT,
  goal_message_id       TEXT,
  goal_updated_at       TIMESTAMPTZ,
  joined_at             TIMESTAMPTZ DEFAULT NOW(),
  created_at            TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────
-- 打卡表
-- ─────────────────────────────────────────
CREATE TABLE checkins (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  member_id        UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
  content          TEXT NOT NULL,
  date             DATE NOT NULL,
  week_number      INT NOT NULL,
  channel_id       TEXT,
  message_id       TEXT,
  completed_goals  JSONB DEFAULT '[]'::jsonb,
  goal_coverage    TEXT,
  created_at       TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(member_id, date)
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
-- 索引
-- ─────────────────────────────────────────
CREATE INDEX idx_checkins_date     ON checkins(date);
CREATE INDEX idx_checkins_member   ON checkins(member_id);
CREATE INDEX idx_checkins_week     ON checkins(week_number);
CREATE INDEX idx_members_discord   ON members(discord_id);

-- =============================================
-- 週排行榜 Function
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
  ar.reply AS ai_reply,
  c.member_id
FROM checkins c
JOIN members m ON m.id = c.member_id
LEFT JOIN ai_replies ar ON ar.checkin_id = c.id
WHERE c.date = (NOW() AT TIME ZONE COALESCE(m.timezone, 'Asia/Taipei'))::date
ORDER BY c.id, ar.created_at DESC;

CREATE OR REPLACE VIEW daily_stats AS
SELECT
  date,
  COUNT(DISTINCT member_id) AS checkin_count
FROM checkins
WHERE date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY date
ORDER BY date;

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
-- =============================================
ALTER TABLE members    ENABLE ROW LEVEL SECURITY;
ALTER TABLE checkins   ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_replies ENABLE ROW LEVEL SECURITY;

CREATE POLICY "allow_read" ON members    FOR SELECT USING (true);
CREATE POLICY "allow_read" ON checkins   FOR SELECT USING (true);
CREATE POLICY "allow_read" ON ai_replies FOR SELECT USING (true);
