-- =============================================
-- Migration 003: 成員目標欄位
-- 支援 weekly-goals channel 的 12 週目標與討論串 summary
-- 在 Supabase Dashboard > SQL Editor 執行
-- =============================================

ALTER TABLE members
  ADD COLUMN IF NOT EXISTS goal_12week_summary   TEXT,   -- 12 週總目標的 AI summary（2-3 句，大方向）
  ADD COLUMN IF NOT EXISTS goal_thread_current   TEXT,   -- 最新一週的週目標摘要（AI 打卡回覆使用）
  ADD COLUMN IF NOT EXISTS goal_thread_history   TEXT,   -- 所有討論串回覆原文合併（未來 RAG 使用）
  ADD COLUMN IF NOT EXISTS goal_message_id       TEXT,   -- weekly-goals 主訊息 ID（用於對應更新）
  ADD COLUMN IF NOT EXISTS goal_updated_at       TIMESTAMPTZ;  -- 最後更新時間

-- 移除舊欄位（若已存在）
ALTER TABLE members DROP COLUMN IF EXISTS goal_thread_summary;
