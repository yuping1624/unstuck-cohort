-- 排行榜改為「活動第 N 週」：只統計 week_start <= date < week_end
-- 執行後 Bot 的 !leaderboard 會依「求職 12 週」的週次計算，與標題「第 N 週」一致
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
