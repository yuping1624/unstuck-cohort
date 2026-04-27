-- Migration 004: 打卡目標完成紀錄
-- 在 Supabase Dashboard > SQL Editor 執行

ALTER TABLE checkins
  ADD COLUMN IF NOT EXISTS completed_goals JSONB DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS goal_coverage   TEXT;
-- goal_coverage: 'full' | 'partial' | 'none' | 'bonus'
