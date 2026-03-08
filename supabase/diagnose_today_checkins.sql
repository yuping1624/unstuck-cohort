-- =============================================
-- 診斷：為什麼 Dashboard「今日打卡」抓不到我的紀錄？
-- 在 Supabase Dashboard > SQL Editor 貼上，一次執行全部，看結果
-- =============================================

-- 1) 目前「今天」在各地時區是幾號？（看你的打卡日期有沒有被算成「今天」）
SELECT
  (NOW() AT TIME ZONE 'UTC')::date AS today_utc,
  (NOW() AT TIME ZONE 'Asia/Taipei')::date AS today_taipei,
  (NOW() AT TIME ZONE 'America/New_York')::date AS today_newyork,
  (NOW() AT TIME ZONE 'America/Toronto')::date AS today_toronto;

-- 2) 最近 10 筆打卡：誰打的、打卡存的 date、該成員的 timezone
--    若你的 timezone 是 Asia/Taipei 但你在美東，打卡會被存成「台灣的今天」的日期
SELECT
  c.date AS 打卡日期,
  c.content AS 內容,
  m.display_name AS 成員,
  m.timezone AS 成員時區,
  c.created_at AS 寫入時間
FROM checkins c
JOIN members m ON m.id = c.member_id
ORDER BY c.created_at DESC
LIMIT 10;

-- 3) 今日打卡 view 實際回傳幾筆？（若這裡是 0，Dashboard 就會是 0）
SELECT COUNT(*) AS 今日打卡筆數 FROM today_checkins;

-- 若筆數 > 0，可看明細：
-- SELECT * FROM today_checkins;

-- 4) 成員的 timezone 一覽（若你在美東/加拿大，timezone 應為 America/New_York 或 America/Toronto，不是 Asia/Taipei）
SELECT display_name, timezone FROM members ORDER BY display_name;

-- =============================================
-- 若發現問題：你的 timezone 是 Asia/Taipei 但你在美東
-- 請在 SQL Editor 單獨執行（把 '你的Discord顯示名' 改成你的名字）：
--
-- UPDATE members
-- SET timezone = 'America/New_York'
-- WHERE display_name = '你的Discord顯示名';
--
-- 改完後 Bot 之後的打卡會用美東的「今天」存；舊的打卡日期不會自動改。
-- 再按 Dashboard 的「重新整理」看今日打卡是否出現。
-- =============================================
