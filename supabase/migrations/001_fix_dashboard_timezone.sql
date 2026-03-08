-- =============================================
-- 修正 Dashboard 時區：今日 / 本週 改為「每位成員的當地日期」
-- 在 Supabase Dashboard > SQL Editor 貼上執行一次即可
-- 這樣美東 3/8 晚上打卡會顯示在 3/8，不會被算成台灣的 3/9
-- =============================================

-- 今日打卡：該成員「當地今天」的紀錄（c.date 本來就是成員當地日期，用 m.timezone 判斷「現在在當地是不是今天」）
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

-- 成員總覽：本週＝該成員當地「本週一～日」內的打卡數
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
