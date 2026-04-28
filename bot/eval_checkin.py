"""
Eval script for daily check-in reply prompt.
Tests _generate_reply() directly with fixed strategy + analysis pairs.

Usage: python eval_checkin.py
"""
import os
import json
import time
import sys
from pathlib import Path
from dotenv import load_dotenv
from google import genai

# Import _generate_reply from bot.py without starting the bot
sys.path.insert(0, str(Path(__file__).parent))
load_dotenv()

# Patch env vars before importing bot
os.environ.setdefault("DISCORD_TOKEN", "x")
os.environ.setdefault("SUPABASE_URL", "https://placeholder.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "placeholder")

from bot import _generate_reply  # noqa: E402

ai_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


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
        "content": "感覺這週什麼都沒做，好像原地踏步",
        "strategy": "reflect_progress",
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
    ("no_empty_praise", "回覆是否完全沒有空洞稱讚？空洞稱讚包括：太棒了/很棒/非常有心/好厲害/great job/so proud/impressive/keep it up/can't wait to see more/你真的很努力。若出現任何這類詞彙則為 false。"),
    ("no_restatement", "回覆是否沒有把打卡內容原封不動地複述一遍？例如「看到你今天完成了 X，做了 Y」就是複述，應判為 false。簡短引用某個具體細節來回應則可以，不算複述。"),
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
            reply = call_with_retry(lambda c=case: _generate_reply(
                strategy=c["strategy"],
                analysis=c["analysis"],
                content=c["content"],
                display_name=c["display_name"],
                streak=3,
                goal_12week=c["goal_12week"],
                goal_thread=c["goal_thread"],
                is_english=c["is_english"],
            ))
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
