# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Discord job-search support bot (Python) paired with a Next.js admin/member dashboard, backed by Supabase (PostgreSQL). The system supports a 12-week career community with daily check-ins, AI-powered replies, streak tracking, and leaderboards.

- **Bot**: GCE e2-micro deployment (us-central1, free tier), `bot/` directory
- **Dashboard**: Vercel deployment, `dashboard/` directory
- **Database**: Supabase (schema + migrations in `supabase/`)

## Commands

### Bot (Python)
```bash
cd bot/
pip install -r requirements.txt
python bot.py                   # Run bot
python recompute_streaks.py     # Manually recalculate all member streaks
```

### Dashboard (Next.js)
```bash
cd dashboard/
npm install
npm run dev      # http://localhost:3000
npm run build
npm run lint
```

### Database
Migrations are applied **manually** via the Supabase Dashboard SQL Editor — there is no automated migration runner. Files in `supabase/migrations/` must be run in order.

## Architecture

### Data Flow
1. Member posts in a check-in Discord channel → bot saves to `checkins` table with member's local date
2. Bot fetches member's goal context (`goal_12week_summary`, `goal_thread_current`) + this week's check-ins from DB
3. Bot calls Gemini API for an AI reply (with memory context) → stored in `ai_replies` table
4. Bot updates streak counters in `members` table
5. Dashboard reads from Supabase views (`member_overview`, `today_checkins`, `daily_stats`)
6. `/api/insights` calls Gemini to generate admin analytics

**Goal Sync Flow:**
- Member posts/edits in `#12週目標` Forum → bot auto-updates `goal_12week_summary` (main post) or `goal_thread_current` / `goal_thread_history` (thread replies)
- `!syncgoals` admin command: one-time scan of all historical `#12週目標` posts to backfill goal summaries

### Bot (`bot/bot.py`)
- Check-in channels: `CHECKIN_CHANNELS` constant (messages auto-trigger check-in logic)
- Chat channels: `CHAT_CHANNELS` (bot responds when @mentioned)
- AI model: `gemini-2.5-flash-lite` via `google-genai`
- Scheduled tasks: daily reminder (members who haven't checked in), weekly Sunday summary
- `!syncgoals` admin command: one-time scan of `#12週目標` Forum, backfills AI goal summaries for all members
- `!deletecheckin` admin command: deletes today's check-in for a member (testing use only), also resets streak by -1
- Group start date: `2026-03-09` — week numbers (0–12) computed from this anchor

### Timezone Handling (Critical)
- Every member has a `timezone` field (e.g., `"Asia/Taipei"`, `"America/Toronto"`)
- All date logic uses the **member's local timezone**, not UTC
- Streaks are consecutive local dates; week numbers are computed per-member timezone
- SQL views use `AT TIME ZONE` for timezone-aware queries

### Dashboard (`dashboard/`)
- `app/page.tsx` — Member view: no query param = instructions, `?discord_id=xxx` = personal stats
- `app/admin/page.tsx` — Password-protected admin panel (tabs: today, members, AI insights)
- `app/api/stats/route.ts` — `force-dynamic`, no caching (always fresh data)
- `app/api/insights/route.ts` — Gemini-powered analytics for admin
- All Supabase calls use `anon` key on client, `service_role` key server-side only

### Database
- `members` — profiles, timezone, streak fields, goal summaries (`goal_12week_summary`, `goal_thread_current`, `goal_thread_history`, `goal_message_id`, `goal_updated_at`)
- `checkins` — one row per member per local date (unique constraint on `member_id, date`)
- `ai_replies` — linked to checkins
- Views: `today_checkins`, `daily_stats`, `member_overview`
- Function: `weekly_leaderboard(week_start, week_end)` — returns top 20 by check-in count

## Environment Variables

**Bot (`bot/.env`):**
```
DISCORD_TOKEN=
SUPABASE_URL=
SUPABASE_KEY=          # service_role key
GEMINI_API_KEY=
DASHBOARD_URL=         # optional, enables !me command
```

**Dashboard (`dashboard/.env.local`):**
```
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
GEMINI_API_KEY=
ADMIN_PASSWORD=
```

## Key Constraints

- `SUPABASE_KEY` in bot must be the `service_role` key (RLS bypass); the dashboard uses `anon` key for public reads
- Week number logic is tied to `GROUP_START_DATE = 2026-03-09`; changing this affects leaderboard and all week calculations
- The `checkins` table has a unique constraint on `(member_id, date)` — duplicate check-ins on the same local date are silently ignored by the bot (returns existing row)
- `#12週目標` must be a **Forum channel** — the bot uses `thread.owner_id` to identify the post author; regular text channels are not supported for goal sync
- Goal summaries use Gemini `gemini-2.5-flash-lite`; texts ≤200 chars are stored as-is, longer texts are summarized
