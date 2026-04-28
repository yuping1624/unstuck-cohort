"""
Standalone test script for generate_weekly_report().
Usage: python test_report.py
Requires: GEMINI_API_KEY in bot/.env (or set as env var)
"""
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

GEMINI_KEY = os.environ["GEMINI_API_KEY"]
ai_client = genai.Client(api_key=GEMINI_KEY)


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


# ── Test cases ──────────────────────────────────────────────────────────────

CASES = [
    {
        "label": "Vicky — Final Interview + market anxiety",
        "display_name": "Vicky",
        "goal_12week": "在12週內拿到一份理想的全職工作 offer",
        "goal_thread": "本週目標：投遞5間公司，更新LinkedIn，準備面試",
        "checkins": [
            {"date": "2026-04-21", "content": "今天面試了一間公司，感覺還不錯，但看到Meta大裁員的新聞有點心慌"},
            {"date": "2026-04-23", "content": "收到第一間的Final Interview通知！很開心但也有點緊張，調整了CV格式"},
            {"date": "2026-04-25", "content": "第二間面試完了。最近有點心累，擔心市場環境，投遞數量沒有達標"},
        ],
    },
    {
        "label": "Cinie — Weekly goal says job search, check-ins show something else",
        "display_name": "Cinie",
        "goal_12week": "找到一份全職工作",
        "goal_thread": "本週目標：投遞3間公司，聯繫2位業界朋友",
        "checkins": [
            {"date": "2026-04-21", "content": "今天花時間整理自己的freelance portfolio，更新了作品集網站"},
            {"date": "2026-04-23", "content": "接了一個小案子，客戶反饋很好，決定繼續接更多freelance"},
            {"date": "2026-04-25", "content": "又接了一個案子，收入還不錯，感覺freelance比找工作更適合我現在的狀態"},
        ],
    },
    {
        "label": "Hardy — Deliberate strategic pause",
        "display_name": "Hardy",
        "goal_12week": "轉職到產品經理職位",
        "goal_thread": "本週目標：投遞2間公司，準備PM面試題",
        "checkins": [
            {"date": "2026-04-21", "content": "跟現在的公司談薪水，他們願意加薪留我，我決定暫緩求職觀察看看"},
            {"date": "2026-04-23", "content": "留下來繼續做，但趁這段時間把PM的side project做起來"},
            {"date": "2026-04-25", "content": "side project進度不錯，暫時不投履歷，專注在累積作品"},
        ],
    },
]


def main():
    for case in CASES:
        print(f"\n{'='*60}")
        print(f"TEST: {case['label']}")
        print('='*60)
        result = generate_weekly_report(
            display_name=case["display_name"],
            goal_12week=case["goal_12week"],
            goal_thread=case["goal_thread"],
            checkins=case["checkins"],
        )
        print(result)
        print()


if __name__ == "__main__":
    main()
