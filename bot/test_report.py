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

CRITICAL: Your output must contain ONLY the three emoji-headed sections below. No analysis, no reasoning, no labels, no intermediate steps. Anything that is not part of the final output must remain entirely in your head.

Member: {display_name}
12-week goal (stored, may be outdated): {goal_12week or '(not set)'}
This week's focus / weekly goals (stored): {goal_thread or '(not set)'}
Check-ins this week:
{checkin_lines}

Before writing, reason silently (output nothing) about:

[Compare goals vs check-ins]
The weekly goal is the ANCHOR. Check-ins show what actually happened.
Three relationships:
- Aligned: check-ins match weekly goal
- Gap: check-ins diverge without member stating a direction change → name the gap, don't silently follow check-ins
- Explicit pivot: member clearly states they are changing direction → follow new direction

[Classify state]
FLOWING — deliberate progress, conscious choices, no real block
   Also use FLOWING if member is clearly at a MORE ADVANCED stage than the prep goal assumed
   (e.g. already in active interviews when goal was to start applying — that's ahead, not behind)
STUCK — member is not doing what they committed to, no stated reason
MIXED — real achievement AND a genuine obstacle (not just a quantity shortfall)
PIVOTING — member explicitly states they are shifting to a new direction

Rules:
- A stated reason for pausing = FLOWING or PIVOTING, never avoidance
- Launch Friction = literally can't start. A member who IS interviewing/producing/completing tasks is NOT Launch Friction
- External anxieties (market, layoffs, waiting on others) = Stoic Control Boundary, not a personal block
- MIXED requires both real wins AND a real obstacle

[If STUCK or MIXED, choose ONE precise lens]
Cognitive Overload / Launch Friction (can't start at all) / Learned Helplessness /
Fear of Evaluation / Identity Gap / Meaning Deficit / Progress Blindness (can't see own wins) /
Execution Fragmentation / Stoic Control Boundary / WOOP gap / Goal-Action Gap

[Micro-action source]
Gap cases: bridge gently back to weekly goal
Pivot cases: follow new direction
Never invent goals the member didn't set themselves

[Language]
Traditional Chinese if check-ins are mostly Chinese; English if mostly English.

Now write ONLY the output. Start directly with 🎯. Do not include any analysis or labels.

Use EXACTLY these three headers, no greeting, no sign-off:

🎯 進度快照 / Snapshot:
<ONE sentence. Ultra-brief factual recap. No praise. If there's a gap between goal and check-ins, name it.>

💡 洞見 / Insight:
FLOWING/PIVOTING: Validate the direction (1 sentence). Name what phase they're in and what matters most NOW — a focus, not a problem. 2-3 sentences total.
STUCK/MIXED: Name the specific block and apply the chosen lens. Direct but not harsh. 2-3 sentences. The member should feel seen, not judged.
Goal-Action Gap: Acknowledge what they did do, then name the gap to their weekly goal. One gentle redirect. No lecturing.
IMPORTANT: Never use framework names or jargon (e.g. "斯多葛", "Launch Friction", "WOOP", "Stoic", "Amabile") in the output. Describe the idea in plain everyday language that any member can understand.

🚀 微行動 / Micro-action:
ONE concrete Implementation Intention written entirely in the output language (do NOT mix languages):
Chinese output → 當[具體觸發點]，我會[微小行動]。（不加引號）
English output → "When [specific trigger], I will [tiny behaviour]."
Rules:
- Must be an ACTIVE behaviour: 寫/打/發送/完成/開啟並輸入/打電話 etc.
- FORBIDDEN passive verbs: 看/閱讀/瀏覽/查看/review/browse/read/watch/look at
- Must take ≤2 minutes to START
- Grounded in their real direction (bridge toward weekly goal for gap cases)

Total: 180-230 Chinese characters OR 150-190 English words."""

    return ai_client.models.generate_content(
        model="gemini-2.5-flash",
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
