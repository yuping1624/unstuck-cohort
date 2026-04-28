"""
Eval script for weekly report prompt.
Tests fixed cases covering all scenarios and scores outputs with LLM-as-judge.

Usage: python eval_report.py
"""
import os
import json
from dotenv import load_dotenv
from google import genai

load_dotenv()
ai_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# ── Test cases ────────────────────────────────────────────────────────────────

CASES = [
    {
        "id": "flowing_deliberate_pause",
        "label": "FLOWING — 刻意暫停求職，等待薪資協商結果",
        "display_name": "Alex",
        "goal_12week": "在三個月內找到產品經理職位",
        "goal_thread": "本週投 5 間公司，完成兩次 coffee chat",
        "checkins": [
            {"date": "2026-04-21", "content": "今天跟現任主管談完了，決定留下來談薪資，先把這輪談判走完再說求職的事", "completed_goals": []},
            {"date": "2026-04-23", "content": "薪資協商繼續，主管說下週給答覆，我決定這週暫停投履歷，等結果", "completed_goals": []},
            {"date": "2026-04-25", "content": "協商進展不錯，有望加薪 15%，繼續等待中", "completed_goals": []},
        ],
        "expected_state": "FLOWING",
    },
    {
        "id": "stuck_no_action",
        "label": "STUCK — 目標明確但沒有行動",
        "display_name": "Bella",
        "goal_12week": "轉職成 UX 設計師",
        "goal_thread": "本週完成作品集第二個 case study，投 3 間公司",
        "checkins": [
            {"date": "2026-04-21", "content": "今天很累，沒有做什麼", "completed_goals": []},
            {"date": "2026-04-23", "content": "滑了一些 Behance 上的作品，感覺自己的還不夠好", "completed_goals": []},
            {"date": "2026-04-25", "content": "還是沒動到 case study，不知道從哪裡開始", "completed_goals": []},
        ],
        "expected_state": "STUCK",
    },
    {
        "id": "mixed_progress_and_obstacle",
        "label": "MIXED — 有面試進展但市場焦慮，投遞量不足",
        "display_name": "Carol",
        "goal_12week": "拿到軟體工程師 offer",
        "goal_thread": "本週投 10 間公司，練習英文面試",
        "checkins": [
            {"date": "2026-04-21", "content": "今天面試了兩間，一間感覺不錯，一間比較緊張", "completed_goals": []},
            {"date": "2026-04-23", "content": "收到其中一間 final round 通知！但 Meta 裁員新聞讓我有點慌，擔心市場", "completed_goals": []},
            {"date": "2026-04-25", "content": "調整了履歷，但投遞數量沒達到目標，一直在想 final 要怎麼準備", "completed_goals": []},
        ],
        "expected_state": "MIXED",
    },
    {
        "id": "pivoting_explicit",
        "label": "PIVOTING — 明確從找全職轉向接案",
        "display_name": "Dana",
        "goal_12week": "找到行銷全職工作",
        "goal_thread": "本週投 5 間行銷職位，更新 LinkedIn",
        "checkins": [
            {"date": "2026-04-21", "content": "跟朋友聊完後決定先不找全職了，想先試試接案，這週開始整理我的接案 portfolio", "completed_goals": []},
            {"date": "2026-04-23", "content": "整理了過去的案子，寫了第一個接案項目介紹", "completed_goals": []},
            {"date": "2026-04-25", "content": "接案 portfolio 初版做好了，準備下週開始找潛在客戶", "completed_goals": []},
        ],
        "expected_state": "PIVOTING",
    },
    {
        "id": "goal_action_gap",
        "label": "Goal-Action Gap — 忙於教學，未啟動原定的個人品牌目標",
        "display_name": "Evan",
        "goal_12week": "建立個人品牌，每週發 3 篇 Threads",
        "goal_thread": "本週發 3 篇 Threads，開始約兩個 coffee chat",
        "checkins": [
            {"date": "2026-04-21", "content": "備課備了很久，明天要上課了", "completed_goals": []},
            {"date": "2026-04-23", "content": "上完課好累，睡了很久才恢復", "completed_goals": []},
            {"date": "2026-04-25", "content": "在規劃下次課程的大綱，準備錄影", "completed_goals": []},
        ],
        "expected_state": "Goal-Action Gap",
    },
    {
        "id": "advanced_stage_flowing",
        "label": "FLOWING — 已在積極面試，進度超前準備階段目標",
        "display_name": "Frank",
        "goal_12week": "拿到軟體工程師 offer",
        "goal_thread": "本週刷 10 題 Leetcode，投 5 間公司",
        "checkins": [
            {"date": "2026-04-21", "content": "今天有一個面試，考了 system design，覺得答得不錯", "completed_goals": []},
            {"date": "2026-04-23", "content": "又一個面試，這次是 behavioral，準備了 STAR 方法", "completed_goals": []},
            {"date": "2026-04-25", "content": "等待兩間公司的回覆，繼續準備下一輪", "completed_goals": []},
        ],
        "expected_state": "FLOWING",
    },
]

# ── Report generation (same prompt as bot.py) ─────────────────────────────────

def generate_report(case: dict) -> str:
    checkin_lines = "\n".join(
        f"- [{c['date']}] {c['content']}"
        + (f" (completed: {', '.join(c['completed_goals'])})" if c.get('completed_goals') else "")
        for c in case["checkins"]
    )

    prompt = f"""You are a warm but honest coach for a 12-week goal-achievement group.
Members have diverse goals — job search, career pivot, side projects, skill-building, etc.
Do NOT assume everyone is job-hunting. Follow what each member is actually doing.

CRITICAL: Your output must contain ONLY the three emoji-headed sections below. No analysis, no reasoning, no labels, no intermediate steps. Anything that is not part of the final output must remain entirely in your head.

Member: {case['display_name']}
12-week goal (stored, may be outdated): {case['goal_12week'] or '(not set)'}
This week's focus / weekly goals (stored): {case['goal_thread'] or '(not set)'}
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
Chinese output → 「當[具體觸發點]，我會[微小行動]。」
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


# ── LLM-as-judge ──────────────────────────────────────────────────────────────

CRITERIA = [
    ("no_language_mix", "微行動句子是否完全用單一語言（不混用 When/I will 和中文）？"),
    ("no_jargon", "洞見中是否完全沒有出現心理學術語或英文框架名稱（斯多葛、Launch Friction、WOOP、Stoic、Amabile 等）？"),
    ("active_microaction", "微行動的核心動詞是否為主動行為？即使加上「快速」、「略」等修飾詞，「閱讀」、「瀏覽」、「看」、「查看」、「browse」、「read」、「watch」、「look at」仍屬被動，應判為 false。只有實際操作行為（寫、打、發送、完成、開啟並輸入、回覆、提交）才算主動。"),
    ("no_prompt_leak", "輸出是否完全沒有出現分析過程或 prompt 結構的痕跡？具體判斷：若出現 STEP 1/STEP 2、[Compare]、[Classify]、FLOWING/STUCK/MIXED/PIVOTING 等分類標籤本身、或大量條列式分析，則為 false。正常的教練語氣（例如：『你本週的行動著重於…』、『原訂的目標…』）屬於合理表達，不算洩漏，應判為 true。"),
    ("correct_state", "整體語氣和建議是否符合該成員的實際狀態（FLOWING/STUCK/MIXED/PIVOTING/Gap）？"),
]

def judge(case: dict, report: str) -> dict[str, bool]:
    criteria_text = "\n".join(
        f"{i+1}. {name}: {question}"
        for i, (name, question) in enumerate(CRITERIA)
    )

    prompt = f"""你是一個嚴格的 AI 輸出品質評審。請根據以下標準逐一評分，回傳 JSON。

成員情境：{case['label']}（預期狀態：{case['expected_state']}）
成員週目標：{case['goal_thread']}
成員打卡：
{chr(10).join(f"- {c['content']}" for c in case['checkins'])}

待評分的週報輸出：
{report}

評分標準（每項只能回答 true 或 false）：
{criteria_text}

回傳格式（只回傳 JSON，不要其他文字）：
{{"no_language_mix": true/false, "no_jargon": true/false, "active_microaction": true/false, "no_prompt_leak": true/false, "correct_state": true/false}}"""

    response = ai_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    ).text.strip()

    # strip markdown code fences if present
    if response.startswith("```"):
        response = response.split("```")[1]
        if response.startswith("json"):
            response = response[4:]

    return json.loads(response)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    total_score = 0
    max_score = len(CASES) * len(CRITERIA)

    print(f"\n{'='*70}")
    print(f"  週報 Eval — {len(CASES)} 個案例 × {len(CRITERIA)} 個標準")
    print(f"{'='*70}\n")

    for case in CASES:
        print(f"▶ {case['label']}")
        print(f"  生成中...", end="", flush=True)

        report = generate_report(case)
        scores = judge(case, report)

        criteria_names = [name for name, _ in CRITERIA]
        case_score = sum(scores.get(name, False) for name in criteria_names)
        total_score += case_score

        icons = {name: "✅" if scores.get(name) else "❌" for name in criteria_names}
        labels = ["無混語", "無術語", "主動行動", "無prompt洩漏", "狀態正確"]

        print(f"\r  ", end="")
        print("  ".join(f"{icons[n]} {l}" for n, l in zip(criteria_names, labels)), end="")
        print(f"  [{case_score}/{len(CRITERIA)}]")

        if any(not scores.get(n) for n in criteria_names):
            print(f"\n  --- 輸出 ---\n{report}\n  -----------\n")

        print()

    pct = int(total_score / max_score * 100)
    print(f"{'='*70}")
    print(f"  總分：{total_score}/{max_score}  ({pct}%)")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
