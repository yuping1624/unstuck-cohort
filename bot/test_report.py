"""
Standalone test script for generate_weekly_report().
Fetches real member data from Supabase and runs the report for all eligible members.

Usage: python test_report.py
Requires: GEMINI_API_KEY, SUPABASE_URL, SUPABASE_KEY in bot/.env
"""
import os
from datetime import date, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from google import genai
from supabase import create_client

load_dotenv()

ai_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])


def generate_weekly_report(display_name: str, goal_12week: str, goal_thread: str,
                            checkins: list[dict]) -> str:
    checkin_lines = "\n".join(
        f"- [{c['date']}] {c['content'][:100]}"
        + (f" (completed: {', '.join(c['completed_goals'])})" if c.get('completed_goals') else "")
        for c in checkins
    ) or "(no check-ins this week)"

    prompt = f"""You are a warm but honest coach for a 12-week goal-achievement group.
Members have diverse goals — job search, career pivot, side projects, skill-building, etc.
Do NOT assume everyone is job-hunting. Follow what each member is actually doing.

Member: {display_name}
12-week goal (stored, may be outdated): {goal_12week or '(not set)'}
This week's focus / weekly goals (stored): {goal_thread or '(not set)'}
Check-ins this week (most reliable signal of actual direction):
{checkin_lines}

═══════════════════════════════════
STEP 1 — INTERNAL ANALYSIS (do NOT output anything from this step):
═══════════════════════════════════

A. Compare weekly goals vs. check-ins — identify alignment or gap.
   The weekly goal is the ANCHOR (what the member committed to this week).
   Check-ins show what actually happened.
   Three possible relationships:
   a) Aligned — check-ins match the weekly goal → proceed normally
   b) Gap — check-ins diverge from weekly goal WITHOUT the member stating a direction change
      → This is a meaningful signal. The member is drifting from their own commitment.
        Name the gap in Step C. Do NOT silently follow the check-ins.
   c) Explicit pivot — member clearly states in check-ins they are changing direction
      → Follow the new direction. Mark as PIVOTING.

B. Determine the member's actual state:
   → FLOWING: deliberate strategic progress, conscious choices, no real block
   → STUCK: genuine block — member is not doing what they said they wanted to do, no stated reason
   → MIXED: real achievements this week AND a genuine obstacle worth naming
   → PIVOTING: member explicitly states they are shifting to a new direction

   Rules:
   - If the member states a reason for pausing (e.g. "staying at current job after negotiation",
     "pausing X to focus on Y"), treat as FLOWING or PIVOTING — never as avoidance.
   - MIXED requires BOTH real achievement AND a real obstacle. Do not label MIXED if the only
     issue is a quantity shortfall against a target.
   - A member who IS taking action (interviewing, producing work, completing tasks) is NOT
     experiencing "Launch Friction" — Launch Friction = can't start at all.
   - External factors (market conditions, waiting for responses, others' decisions) are NOT
     the member's block. If anxiety about uncontrollable factors is affecting them, use
     "Stoic Control Boundary" lens.

C. If STUCK or MIXED, name the block precisely:
   ✗ vague → ✓ "completed interviews but has not applied to new positions despite weekly goal"
   Then choose ONE lens that fits:
   Cognitive Overload / Launch Friction (can't start) / Learned Helplessness (Seligman) /
   Fear of Evaluation / Identity Gap (James Clear) / Meaning Deficit (Frankl) /
   Progress Blindness (Amabile — can't see own wins) / Execution Fragmentation /
   Stoic Control Boundary (anxiety over uncontrollables) / WOOP gap (no concrete plan) /
   Goal-Action Gap (check-ins diverged from weekly commitment without stated reason)

D. Micro-action must come from the member's actual weekly goal AND check-ins combined.
   For gap cases (1Ab): the micro-action should gently bridge back to the weekly goal.
   For pivots (1Ac): follow the new direction only.
   Do not invent goals the member did not set themselves.

E. Decide output language: Traditional Chinese if check-ins are mostly Chinese; English if mostly English.

═══════════════════════════════════
STEP 2 — OUTPUT (write in the language from Step 1E):
═══════════════════════════════════

Use EXACTLY these three headers, no greeting, no sign-off:

🎯 進度快照 / Snapshot:
<ONE sentence. Ultra-brief factual recap. No praise. If there's a gap between goal and check-ins, name it.>

💡 洞見 / Insight:
FLOWING/PIVOTING: Validate the direction (1 sentence). Name what phase they're in and what matters most NOW — a focus, not a problem. 2-3 sentences total.
STUCK/MIXED: Name the specific block and apply the chosen lens. Direct but not harsh. 2-3 sentences. The member should feel seen, not judged.
Goal-Action Gap: Acknowledge what they did do, then name the gap to their weekly goal. One gentle redirect. No lecturing.

🚀 微行動 / Micro-action:
ONE Implementation Intention:
"When [specific trigger], I will [tiny behaviour]."
Must take ≤2 minutes to START. Grounded in their real direction (bridge toward weekly goal for gap cases).

Total: 180-230 Chinese characters OR 150-190 English words."""

    return ai_client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt
    ).text.strip()


def get_last_week_range(tz_str: str) -> tuple[date, date]:
    """Return (last_monday, last_sunday) in member's local timezone."""
    from datetime import datetime
    today = datetime.now(ZoneInfo(tz_str)).date()
    last_sunday = today - timedelta(days=today.weekday() + 1)
    last_monday = last_sunday - timedelta(days=6)
    return last_monday, last_sunday


def main():
    members_res = supabase.table("members").select(
        "id, discord_id, display_name, timezone, goal_12week_summary, goal_thread_current"
    ).execute()
    members = members_res.data or []

    for member in members:
        name = member.get("display_name", "?")
        tz_str = member.get("timezone") or "Asia/Taipei"
        last_monday, last_sunday = get_last_week_range(tz_str)

        checkins_res = supabase.table("checkins") \
            .select("date, content, completed_goals") \
            .eq("member_id", member["id"]) \
            .gte("date", last_monday.strftime("%Y-%m-%d")) \
            .lte("date", last_sunday.strftime("%Y-%m-%d")) \
            .order("date") \
            .execute()
        checkins = checkins_res.data or []

        has_any_goal = bool(member.get("goal_12week_summary") or member.get("goal_thread_current"))
        if not has_any_goal or len(checkins) == 0:
            print(f"\n{'─'*50}")
            print(f"⏭  {name} — 跳過（無目標或無打卡）")
            continue

        print(f"\n{'='*60}")
        print(f"📬 週報預覽 — {name}  [{last_monday} ~ {last_sunday}]  ({len(checkins)} 次打卡)")
        print('='*60)
        try:
            result = generate_weekly_report(
                display_name=name,
                goal_12week=member.get("goal_12week_summary", ""),
                goal_thread=member.get("goal_thread_current", ""),
                checkins=checkins,
            )
            print(result)
        except Exception as e:
            print(f"❌ 生成失敗: {e}")


if __name__ == "__main__":
    main()
