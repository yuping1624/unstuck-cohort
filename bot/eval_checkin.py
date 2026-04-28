"""
Eval script for daily check-in reply prompt.
Tests _generate_reply() directly with fixed strategy + analysis pairs.
Does NOT import bot.py to avoid starting the Discord bot.

Usage: python eval_checkin.py
"""
import os
import json
import time
from dotenv import load_dotenv
from google import genai

load_dotenv()
ai_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

ENABLE_ENGLISH_CORRECTION = True


def call_with_retry(fn, retries=4, backoff=3):
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            if attempt == retries - 1:
                raise
            wait = backoff * (2 ** attempt)
            print(f"\r  ⚠️  API 錯誤（{e}），{wait}s 後重試...", end="", flush=True)
            time.sleep(wait)


# ── Copied from bot.py (keep in sync) ────────────────────────────────────────

_STRATEGY_CONFIGS = {
    "support_rest": {
        "instruction": "This person is exhausted. Validate only. No advice, no 'keep going'. 1-2 warm sentences. End with something like 'today, just being here is enough'.",
    },
    "affirm_resilience": {
        "instruction": "This person had a setback AND took a recovery action (e.g. {recovery_action}). Acknowledge the difficulty (1 sentence). Then specifically name that recovery action as genuine resilience — not 'despite X you did Y', but 'you know how to take care of yourself'. Connect to identity. No job-search advice. Do NOT end with forward-looking cheer ('keep it up', '繼續保持', 'you'll get there').",
    },
    "reframe_attribution": {
        "instruction": "Signs of learned helplessness. Gently challenge the permanent/global attribution. This setback is specific and temporary, not proof they'll always fail. 2-3 sentences. No toxic positivity.",
    },
    "validate_ground": {
        "instruction": "Person is venting and aware they're struggling. Fully validate the feeling (1 sentence). Then offer ONE optional tiny grounding action, framed as a choice not an instruction.",
    },
    "explore_meaning": {
        "instruction": "Person questions if their goal direction is right. Do NOT give action advice. Ask ONE open question to reconnect with their 'why'. Warm, non-judgmental. 1-2 sentences + 1 question.",
    },
    "identity_affirmation": {
        "instruction": "Identity gap — target role doesn't feel like 'who I am yet'. Connect their specific action today to identity formation: 'every time you [what they did], you're becoming the kind of person who...'. 2-3 sentences.",
    },
    "reflect_progress": {
        "instruction": "Person can't see their own progress. Name SPECIFIC completed things from key_observation and hidden_progress. Do not invent. Make them feel genuinely seen. 2-3 sentences.",
    },
    "woop_obstacle": {
        "instruction": "Person is announcing plans. Affirm the plan (1 sentence). Then ask ONE specific question about the most likely obstacle. Do not lecture.",
    },
    "gentle_name_fear": {
        "instruction": "Person is likely avoiding a scary action without realising it. Gently name the avoidance pattern without judgment. 2 sentences max. Don't push to act, don't collude with avoidance.",
    },
    "practical_micro_action": {
        "instruction": "Execution-blocked but emotionally ready. Give ONE Implementation Intention: 'When [specific trigger], I will [tiny behaviour that takes ≤2 min to start]'. More specific than what they already planned. End on the micro-action itself — no pep talk, no '加油', no 'you can do it' after.",
    },
    "productive_discomfort": {
        "instruction": "Late-stage comfortable routine (week 9+). Acknowledge consistency (1 sentence). Then ask ONE question inviting a slight stretch. Not harsh, just a gentle nudge.",
    },
    "encourage": {
        "instruction": "Pick ONE specific thing they wrote and react to it like a thoughtful friend who actually read it — not 'great job', not a summary, not 'you're so hardworking'. A real reaction: a question, a brief observation, a small connection to their goal, or a gentle nudge. 2-3 sentences. FORBIDDEN: restating what they did, empty praise (太棒了/very impressive/非常有心/proud of you/awesome/that's great), 'keep it up', 'can't wait to see more', '一起加油', '繼續保持'.",
    },
}


def _generate_reply(
    strategy: str,
    analysis: dict,
    content: str,
    display_name: str,
    streak: int,
    goal_12week: str,
    goal_thread: str,
    is_english: bool,
) -> str:
    config = _STRATEGY_CONFIGS.get(strategy, _STRATEGY_CONFIGS["encourage"])
    instruction = config["instruction"]

    if strategy == "affirm_resilience":
        recovery_action = analysis.get("recovery_action", "")
        instruction = instruction.replace("{recovery_action}", recovery_action or "a recovery action")

    if is_english:
        lang_instruction = "IMPORTANT: Write your reply entirely in English. Natural tone, like a native speaker. Casual and conversational."
    else:
        lang_instruction = "IMPORTANT: Write your reply entirely in Traditional Chinese (繁體中文). Natural tone, casual like a friend."

    streak_note = f"\nNote: This is their {streak}-day check-in streak." if streak > 1 else ""

    correction_note = ""
    if ENABLE_ENGLISH_CORRECTION and is_english:
        correction_note = "\nIf the member's English has obvious unnatural phrasing (Chinglish), add ONE brief P.S. showing a more natural way to say it. Preserve their tone. Don't correct common casual abbreviations (gonna, wanna, btw, etc.)."

    key_obs = analysis.get("key_observation", content[:100])
    hidden = analysis.get("hidden_progress", "")
    memory_parts = []
    if goal_12week:
        memory_parts.append(f"12-week goal: {goal_12week}")
    if goal_thread:
        memory_parts.append(f"This week's focus: {goal_thread}")
    memory_section = "\n".join(memory_parts)

    prompt = f"""You are a warm, genuine accountability group assistant replying to a member's daily check-in.

Member: {display_name}
Check-in: {content}
Key observation: {key_obs}
{"Hidden progress: " + hidden if hidden else ""}
{memory_section}
{streak_note}

Strategy instruction: {instruction}

{lang_instruction}
{correction_note}

Global rules (apply regardless of strategy):
- Do NOT restate or summarise what the member just said
- Do NOT use empty praise: 太棒了 / 很棒 / 非常有心 / 好厲害 / great job / so proud / impressive / keep it up / can't wait to see more
- React to the SPECIFIC content, not the general fact that they checked in

Output max 4 sentences. Output ONLY the reply, no prefix."""

    return call_with_retry(lambda: ai_client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt,
    ).text.strip())


# ── Test cases ────────────────────────────────────────────────────────────────

CASES = [
    {
        "id": "encourage_specific_achievement",
        "label": "encourage — 完成具體成果，測試是否有空洞稱讚",
        "strategy": "encourage",
        "content": "今天晚上幾乎都在精進村長，週報功能第一版算是開發出來了，希望大家可以幫我看看有沒有什麼奇怪的地方或是想要的回應。同時也思考接下來群組的走向，目前徵集大家的意見中～做這個 project 很開心，但我應該要去洗澡睡覺了😂",
        "display_name": "Yuna",
        "analysis": {"key_observation": "完成週報功能第一版，在思考群組未來走向", "hidden_progress": ""},
        "goal_12week": "打造 Discord 求職支援社群",
        "goal_thread": "完成 bot 週報功能",
        "is_english": False,
    },
    {
        "id": "support_rest_exhausted",
        "label": "support_rest — 精疲力竭，不應給建議",
        "strategy": "support_rest",
        "content": "今天真的累爆了，什麼都沒做，只是來打個卡",
        "display_name": "Ben",
        "analysis": {"key_observation": "精疲力竭，無法行動", "hidden_progress": ""},
        "goal_12week": "找到後端工程師工作",
        "goal_thread": "本週投 5 份履歷",
        "is_english": False,
    },
    {
        "id": "affirm_resilience_recovery",
        "label": "affirm_resilience — 挫折後有恢復行動",
        "strategy": "affirm_resilience",
        "content": "面試又被拒絕了，有點難受。但還是強迫自己去跑步，跑完好多了",
        "display_name": "Claire",
        "analysis": {"key_observation": "面試被拒，情緒低落", "hidden_progress": "主動去跑步讓自己恢復", "recovery_action": "去跑步"},
        "goal_12week": "拿到設計師 offer",
        "goal_thread": "本週完成作品集",
        "is_english": False,
    },
    {
        "id": "reflect_progress_cant_see_wins",
        "label": "reflect_progress — 看不見自己進度",
        "strategy": "reflect_progress",
        "content": "感覺這週什麼都沒做，好像原地踏步",
        "display_name": "Dan",
        "analysis": {"key_observation": "認為自己沒有進度", "hidden_progress": "其實完成了兩次面試和一份履歷"},
        "goal_12week": "轉職到產品經理",
        "goal_thread": "本週完成兩次面試",
        "is_english": False,
    },
    {
        "id": "practical_micro_action_blocked",
        "label": "practical_micro_action — 有計畫但卡住，需要具體微行動",
        "strategy": "practical_micro_action",
        "content": "一直想開始寫 cover letter 但每次都拖著，不知道為什麼就是動不了",
        "display_name": "Eva",
        "analysis": {"key_observation": "想寫 cover letter 但執行卡住", "hidden_progress": ""},
        "goal_12week": "找到行銷工作",
        "goal_thread": "本週投 3 份工作",
        "is_english": False,
    },
    {
        "id": "encourage_english",
        "label": "encourage — 英文打卡，測試語言一致性",
        "strategy": "encourage",
        "content": "Finally sent out 3 applications today after procrastinating for a week. Feels good.",
        "display_name": "Frank",
        "analysis": {"key_observation": "Sent 3 applications after a week of procrastination", "hidden_progress": ""},
        "goal_12week": "Land a software engineer role",
        "goal_thread": "Apply to 5 companies this week",
        "is_english": True,
    },
]

# ── Criteria ──────────────────────────────────────────────────────────────────

CRITERIA = [
    ("no_empty_praise", "回覆是否完全沒有空洞稱讚或結尾打氣？包括：太棒了/很棒/非常有心/好厲害/great job/so proud/impressive/awesome/that's great/keep it up/can't wait to see more/你真的很努力/繼續保持/一起加油/你可以的/you can do it。若出現任何這類詞彙則為 false。"),
    ("no_restatement", "回覆是否沒有大量複述打卡內容？注意：『reflect_progress』策略需要先引用成員的感受（如「感覺原地踏步」）再矯正，這是策略需要，不算複述。只有當回覆幾乎只是把打卡內容換句話說、沒有新資訊時，才判為 false。"),
    ("specific_reaction", "回覆是否對打卡內容有具體、真實的回應？例如針對某件事提問、給出觀察、或做出連結。泛泛的「繼續加油」不算具體回應，應判為 false。"),
    ("correct_language", "回覆語言是否與打卡語言一致？中文打卡 → 回覆應為繁體中文；英文打卡 → 回覆應為英文。"),
    ("within_length", "回覆是否在 4 句話以內？"),
]

# ── Judge ─────────────────────────────────────────────────────────────────────

def judge(case: dict, reply: str) -> dict[str, bool]:
    criteria_text = "\n".join(
        f"{i+1}. {name}: {question}"
        for i, (name, question) in enumerate(CRITERIA)
    )

    prompt = f"""你是一個嚴格的 AI 輸出品質評審。請根據以下標準逐一評分，回傳 JSON。

打卡情境：{case['label']}
成員打卡內容：{case['content']}

待評分的 bot 回覆：
{reply}

評分標準（每項只能回答 true 或 false）：
{criteria_text}

回傳格式（只回傳 JSON，不要其他文字）：
{{"no_empty_praise": true/false, "no_restatement": true/false, "specific_reaction": true/false, "correct_language": true/false, "within_length": true/false}}"""

    response = call_with_retry(lambda: ai_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    ).text.strip())

    if response.startswith("```"):
        response = response.split("```")[1]
        if response.startswith("json"):
            response = response[4:]

    return json.loads(response)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    total_score = 0
    max_score = len(CASES) * len(CRITERIA)

    print(f"\n{'='*70}")
    print(f"  打卡回覆 Eval — {len(CASES)} 個案例 × {len(CRITERIA)} 個標準")
    print(f"{'='*70}\n")

    for case in CASES:
        print(f"▶ {case['label']}")
        print(f"  生成中...", end="", flush=True)

        try:
            reply = _generate_reply(
                strategy=case["strategy"],
                analysis=case["analysis"],
                content=case["content"],
                display_name=case["display_name"],
                streak=3,
                goal_12week=case["goal_12week"],
                goal_thread=case["goal_thread"],
                is_english=case["is_english"],
            )
            scores = judge(case, reply)
        except Exception as e:
            print(f"\r  ❌ 生成失敗: {e}\n")
            continue

        criteria_names = [name for name, _ in CRITERIA]
        case_score = sum(scores.get(name, False) for name in criteria_names)
        total_score += case_score

        icons = {name: "✅" if scores.get(name) else "❌" for name in criteria_names}
        labels = ["無空洞稱讚", "無複述", "具體回應", "語言正確", "長度OK"]

        print(f"\r  ", end="")
        print("  ".join(f"{icons[n]} {l}" for n, l in zip(criteria_names, labels)), end="")
        print(f"  [{case_score}/{len(CRITERIA)}]")

        if any(not scores.get(n) for n in criteria_names):
            print(f"\n  --- 回覆 ---\n{reply}\n  -----------\n")

        print()

    pct = int(total_score / max_score * 100)
    print(f"{'='*70}")
    print(f"  總分：{total_score}/{max_score}  ({pct}%)")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
