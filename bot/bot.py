"""
求職 12 週 Discord Bot
功能：打卡收集、AI 回覆、連續天數追蹤、週提醒
"""

import os
import re
import json
import asyncio
import time
from datetime import date, datetime, timedelta, timezone
import discord
from discord.ext import commands, tasks
from supabase import create_client, Client
from google import genai
from google.genai import types as genai_types
from zoneinfo import ZoneInfo  # Python 3.9+ 內建，不需要安裝
from dotenv import load_dotenv

load_dotenv()


# ─────────────────────────────────────────
# 設定
# ─────────────────────────────────────────
DISCORD_TOKEN   = os.environ["DISCORD_TOKEN"]
SUPABASE_URL    = os.environ["SUPABASE_URL"]
SUPABASE_KEY    = os.environ["SUPABASE_KEY"]       # service_role key
GEMINI_KEY      = os.environ["GEMINI_API_KEY"]

# 打卡頻道名稱（可以是多個）
CHECKIN_CHANNELS = {"每日打卡", "daily-micro-action", "test-checkin"}

# 允許 Tag bot 發問/聊天的頻道
CHAT_CHANNELS = {"general", "閒聊", "求職討論"}

# 當使用者用英文打卡/聊天時，是否在回覆中「順帶」友善糾正英文（可選一句）
ENABLE_ENGLISH_CORRECTION = True

# 管理員頻道（bot 發送洞察報告用）
ADMIN_CHANNEL_NAME = "bot-log"

# 不發每日提醒的成員（助教/觀察者角色）
REMINDER_EXCLUDED = {"680760447972147247", "214883164009529344"}  # Zoe-Yeh, Trapper

# Dashboard 網址（選填，用於 !me 產生專屬連結，例如 https://xxx.vercel.app）
DASHBOARD_URL = (os.environ.get("DASHBOARD_URL") or "").strip().rstrip("/")

# 群組開始日期：以「每人所在地區的 3/9」為第 1 天，週數依成員時區計算
GROUP_START_DATE = datetime(2026, 3, 9, tzinfo=timezone.utc)

# Taipei time offset
TZ = timezone(timedelta(hours=8))

# ─────────────────────────────────────────
# 初始化
# ─────────────────────────────────────────
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
ai_client = genai.Client(api_key=GEMINI_KEY)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


# ─────────────────────────────────────────
# 工具函式
# ─────────────────────────────────────────
def week_number_for_member(member_timezone: str) -> int:
    """依成員時區：以該時區的 3/9 00:00 為第 1 天，回傳 1–12 或 0（尚未開始）。"""
    tz = ZoneInfo(member_timezone)
    now = datetime.now(tz)
    start_local = datetime(2026, 3, 9, 0, 0, 0, tzinfo=tz)
    if now < start_local:
        return 0
    delta = now - start_local
    return min(delta.days // 7 + 1, 12)


def current_week() -> int:
    """回傳「參考時區 Asia/Taipei」的週數，用於 embed、週總結等。"""
    return week_number_for_member("Asia/Taipei")


def week_label() -> str:
    """用於 embed 顯示的週數文字（含尚未開始）。"""
    w = current_week()
    if w == 0:
        return "第 0 週（3/9 起為第 1 週）"
    return f"第 {w} 週"


def today_for_member(member_timezone: str) -> str:
    """根據成員時區回傳他的『今天』是幾號"""
    tz = ZoneInfo(member_timezone)
    return datetime.now(tz).strftime("%Y-%m-%d")

def already_checked_in(member_id: str, member_timezone: str) -> bool:
    today = today_for_member(member_timezone)
    result = supabase.table("checkins") \
        .select("id") \
        .eq("member_id", member_id) \
        .eq("date", today) \
        .execute()
    return len(result.data) > 0

def save_checkin(member_id: str, content: str, channel_id: str, message_id: str, member_timezone: str) -> dict:
    today = today_for_member(member_timezone)
    row = {
        "member_id": member_id,
        "content": content,
        "date": today,          # 用成員自己的今天
        "week_number": week_number_for_member(member_timezone),  # 以該成員當地 3/9 起算第幾週
        "channel_id": channel_id,
        "message_id": message_id,
        "created_at": datetime.now(timezone.utc).isoformat(),  # 儲存時間仍用 UTC
    }
    try:
        result = supabase.table("checkins").insert(row).execute()
        return result.data[0]
    except Exception as e:
        # duplicate key：回傳已存在的那筆
        if "23505" in str(e):
            existing = supabase.table("checkins") \
                .select("*") \
                .eq("member_id", member_id) \
                .eq("date", today) \
                .execute()
            if existing.data:
                return existing.data[0]
        raise


def get_or_create_member(discord_id: str, username: str, display_name: str) -> dict:
    result = supabase.table("members") \
        .select("*") \
        .eq("discord_id", discord_id) \
        .execute()

    if result.data:
        return result.data[0]

    new_member = {
        "discord_id": discord_id,
        "username": username,
        "display_name": display_name,
        "joined_at": datetime.now(TZ).isoformat(),
    }
    inserted = supabase.table("members").insert(new_member).execute()
    return inserted.data[0]


def update_streak(member_id: str, member_timezone: str, today_date: str):
    """更新連續打卡天數。用成員當地「昨天」判斷是否連續，避免用台灣時間導致美東等時區算錯。"""
    tz = ZoneInfo(member_timezone)
    yesterday = (datetime.now(tz) - timedelta(days=1)).strftime("%Y-%m-%d")

    result = supabase.table("checkins") \
        .select("date") \
        .eq("member_id", member_id) \
        .gte("date", yesterday) \
        .execute()

    dates = {r["date"] for r in result.data}

    member = supabase.table("members").select("current_streak, longest_streak") \
        .eq("id", member_id).execute().data[0]

    current = member.get("current_streak") or 0
    if yesterday in dates:
        new_streak = current + 1
    else:
        new_streak = 1  # 重新開始

    longest = max(member.get("longest_streak") or 0, new_streak)

    supabase.table("members").update({
        "current_streak": new_streak,
        "longest_streak": longest,
        "last_checkin_date": today_date,
    }).eq("id", member_id).execute()

    return new_streak


def recompute_streaks():
    """依 checkins 表重算所有成員的 current_streak、longest_streak、last_checkin_date。可修正歷史錯誤資料。"""
    members = supabase.table("members").select("id").execute().data
    for m in members:
        mid = m["id"]
        rows = supabase.table("checkins").select("date").eq("member_id", mid).order("date").execute().data
        dates = sorted({r["date"] for r in rows})
        if not dates:
            supabase.table("members").update({
                "current_streak": 0,
                "longest_streak": 0,
                "last_checkin_date": None,
            }).eq("id", mid).execute()
            continue
        last_date = dates[-1]
        # current_streak: 從最後一天往前數連續幾天
        cur = 1
        d = datetime.fromisoformat(last_date).date()
        for i in range(len(dates) - 2, -1, -1):
            prev = datetime.fromisoformat(dates[i]).date()
            if (d - prev).days == 1:
                cur += 1
                d = prev
            else:
                break
        # longest_streak: 掃一遍找最長連續區間
        longest = 1
        run = 1
        for i in range(1, len(dates)):
            a = datetime.fromisoformat(dates[i - 1]).date()
            b = datetime.fromisoformat(dates[i]).date()
            if (b - a).days == 1:
                run += 1
                longest = max(longest, run)
            else:
                run = 1
        supabase.table("members").update({
            "current_streak": cur,
            "longest_streak": longest,
            "last_checkin_date": last_date,
        }).eq("id", mid).execute()
    print("recompute_streaks done.")


def _is_mainly_english(text: str) -> bool:
    """簡單判斷內容是否主要為英文（用於是否啟用英文糾正提示）"""
    cleaned = "".join(c for c in text if c.isalpha())
    if not cleaned:
        return False
    ascii_letters = sum(1 for c in cleaned if ord(c) < 128)
    return ascii_letters / len(cleaned) >= 0.7


# ─────────────────────────────────────────
# 多節點 Agent 設計
# ─────────────────────────────────────────

_STRATEGY_CONFIGS = {
    "support_rest": {
        "instruction": "This person is exhausted. Validate only. No advice, no 'keep going'. 1-2 warm sentences. End with something like 'today, just being here is enough'.",
    },
    "affirm_resilience": {
        "instruction": "This person had a setback AND took a recovery action (e.g. {recovery_action}). Acknowledge the difficulty (1 sentence). Then specifically name that recovery action as genuine resilience — not 'despite X you did Y', but 'you know how to take care of yourself'. Connect to identity with a statement like 'this is who you are'. No job-search advice. Do NOT end with any forward-looking suggestion starting with 繼續/keep/continue/你就會/you'll.",
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
        "instruction": "Pick ONE specific thing they wrote and react to it like a thoughtful friend who actually read it. A real reaction: a question, a brief observation, or a small connection to their goal. 2-3 sentences. The reply must end on the question or observation — never on a compliment or a cheer. FORBIDDEN anywhere in the reply: 太棒了/很棒/非常有心/好厲害/awesome/great/impressive/proud/keep it up/can't wait/很期待/繼續保持/一起加油/你可以的/期待看到.",
    },
}


def _analyze_checkin(
    content: str,
    display_name: str,
    goal_12week: str,
    goal_thread: str,
    week_checkins: list,
    week_number: int,
) -> dict:
    """Node 1: Analyze the check-in and return structured analysis as a dict."""
    _safe_defaults = {
        "emotional_state": "neutral",
        "block_type": "none",
        "mode": "reporting",
        "energy_for_advice": True,
        "key_observation": content[:100],
        "hidden_progress": "",
        "has_recovery_action": False,
        "recovery_action": "",
        "completed_goals": [],
        "goal_coverage": "none",
    }

    memory_parts = []
    if goal_12week:
        memory_parts.append(f"12-week goal: {goal_12week}")
    if goal_thread:
        memory_parts.append(f"This week's focus: {goal_thread}")
    if week_checkins:
        checkins_text = "\n".join(f"- {c}" for c in week_checkins)
        memory_parts.append(f"Other check-ins this week:\n{checkins_text}")
    memory_section = "\n\n".join(memory_parts)

    prompt = f"""You are an expert career coach and psychologist analyzing a check-in message from a member of a 12-week goal accountability group.

Member: {display_name}
Week number: {week_number}
Check-in content: {content}

{memory_section}

Analyze this check-in and return a JSON object with the following fields:

- emotional_state: one of "exhausted|avoidance|helpless|neutral|positive"
  - exhausted = physically or mentally drained
  - avoidance = avoiding a scary action (fear of rejection/evaluation) disguised as "nothing done"
  - helpless = repeated failures causing "nothing works" belief
  - neutral = stable, matter-of-fact
  - positive = energised, motivated

- block_type: one of "execution|meaning_crisis|identity_gap|progress_blindness|none"
  - execution = knows what to do but isn't doing it
  - meaning_crisis = questioning if goal direction is right
  - identity_gap = target role doesn't feel like "who I am"
  - progress_blindness = real progress exists but member can't see it
  - none = not blocked

- mode: one of "reporting|planning|venting"
  - reporting = describing what happened
  - planning = announcing future intentions
  - venting = primarily expressing emotion

- energy_for_advice: boolean — false if emotional_state is "exhausted" or "helpless"

- key_observation: string — the most specific thing worth responding to in this check-in

- hidden_progress: string — real progress the member made but doesn't recognise, or empty string if none

- has_recovery_action: boolean — true if member took any self-care or recovery action (exercise, rest, cooking, etc.) even if unrelated to official goals

- recovery_action: string — description of the recovery action, or empty string

- completed_goals: array of strings — specific accomplishments mentioned (e.g. "sent 2 job applications", "went for a run", "finished resume draft") — include ALL goals not just official ones

- goal_coverage: one of "full|partial|none|bonus"
  - full = completed all official weekly goals
  - partial = completed some official weekly goals
  - none = no official goals completed
  - bonus = completed things outside official goals only

Return ONLY valid JSON, no markdown, no explanation."""

    try:
        response = ai_client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json"
            ),
        )
        raw = response.text or ""
        result = json.loads(raw)
        # Ensure all required keys exist with safe defaults
        for k, v in _safe_defaults.items():
            if k not in result:
                result[k] = v
        return result
    except Exception as e:
        print(f"[agent] _analyze_checkin 失敗：{e}")
        return _safe_defaults


def _route(analysis: dict, week_number: int) -> str:
    """Node 2: Pure Python routing — returns strategy string based on analysis."""
    es = analysis.get("emotional_state", "neutral")
    bt = analysis.get("block_type", "none")
    mode = analysis.get("mode", "reporting")
    can_advise = analysis.get("energy_for_advice", True)
    has_recovery = analysis.get("has_recovery_action", False)
    has_hidden = bool(analysis.get("hidden_progress", "").strip())

    if es == "exhausted" and has_recovery:
        return "affirm_resilience"
    if es == "helpless" and has_recovery:
        return "affirm_resilience"
    if es == "exhausted":
        return "support_rest"
    if es == "helpless":
        return "reframe_attribution"
    if mode == "venting" and es == "avoidance":
        return "validate_ground"
    if mode == "venting" and not can_advise:
        return "validate_ground"
    if bt == "meaning_crisis":
        return "explore_meaning"
    if bt == "identity_gap":
        return "identity_affirmation"
    if bt == "progress_blindness" or has_hidden:
        return "reflect_progress"
    if mode == "planning":
        return "woop_obstacle"
    if es == "avoidance" and mode == "reporting":
        return "gentle_name_fear"
    if bt == "execution" and can_advise:
        return "practical_micro_action"
    if week_number >= 9 and bt == "none" and mode == "reporting":
        return "productive_discomfort"
    return "encourage"


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
    """Node 3: Generate the final reply using the chosen strategy."""
    config = _STRATEGY_CONFIGS.get(strategy, _STRATEGY_CONFIGS["encourage"])
    instruction = config["instruction"]

    # Inject recovery_action into affirm_resilience instruction
    if strategy == "affirm_resilience":
        recovery_action = analysis.get("recovery_action", "")
        instruction = instruction.replace("{recovery_action}", recovery_action or "a recovery action")

    # Language instruction
    if is_english:
        lang_instruction = "IMPORTANT: Write your reply entirely in English. Natural tone, like a native speaker. Casual and conversational."
    else:
        lang_instruction = "IMPORTANT: Write your reply entirely in Traditional Chinese (繁體中文). Natural tone, casual like a friend."

    # Streak note
    streak_note = ""
    if streak > 1:
        streak_note = f"\nNote: This is their {streak}-day check-in streak."

    # English correction note
    correction_note = ""
    if ENABLE_ENGLISH_CORRECTION and is_english:
        correction_note = "\nIf the member's English has obvious unnatural phrasing (Chinglish), add ONE brief P.S. showing a more natural way to say it. Preserve their tone. Don't correct common casual abbreviations (gonna, wanna, btw, etc.)."

    # Context about the check-in
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
- Do NOT use empty praise or closing cheers: 太棒了 / 很棒 / 非常有心 / 好厲害 / awesome / great job / so proud / impressive / keep it up / can't wait to see more / 繼續保持 / 一起加油 / 你可以的 / you can do it
- React to the SPECIFIC content, not the general fact that they checked in

Output max 4 sentences. Output ONLY the reply, no prefix."""

    try:
        response = ai_client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
        )
        return response.text or "今天已經成功打卡了！你的努力已經被記錄下來 🙌"
    except Exception as e:
        print(f"[agent] _generate_reply 失敗：{e}")
        return "今天已經成功打卡了！AI 目前暫時無法生成回覆，但你的打卡我都有看到 💪"


def get_ai_reply(
    content: str,
    display_name: str,
    streak: int,
    goal_12week: str = "",
    goal_thread: str = "",
    week_checkins: list = None,
    week_number: int = 0,
) -> str:
    """Orchestrator: runs 3-node agent pipeline and returns reply string."""
    try:
        analysis = _analyze_checkin(
            content=content,
            display_name=display_name,
            goal_12week=goal_12week,
            goal_thread=goal_thread,
            week_checkins=week_checkins or [],
            week_number=week_number,
        )
        strategy = _route(analysis, week_number)
        print(
            f"[agent] {display_name} → {strategy} | "
            f"state={analysis.get('emotional_state')} "
            f"block={analysis.get('block_type')} "
            f"mode={analysis.get('mode')}"
        )
        is_english = _is_mainly_english(content)
        reply = _generate_reply(
            strategy=strategy,
            analysis=analysis,
            content=content,
            display_name=display_name,
            streak=streak,
            goal_12week=goal_12week,
            goal_thread=goal_thread,
            is_english=is_english,
        )
        return reply
    except Exception as e:
        print(f"AI 回覆失敗（get_ai_reply）：{e}")
        return "今天已經成功打卡了！AI 目前暫時無法生成回覆，但你的打卡我都有看到 💪"


def save_ai_reply(checkin_id: str, reply: str):
    supabase.table("ai_replies").insert({
        "checkin_id": checkin_id,
        "reply": reply,
        "created_at": datetime.now(TZ).isoformat(),
    }).execute()


# ─────────────────────────────────────────
# 目標相關工具函式
# ─────────────────────────────────────────
GOAL_CHANNEL_NAME = "weekly-goals"
GOAL_SUMMARY_THRESHOLD = 200  # 超過此字數才做 summary，否則存原文


def _summarize_12week_goal(raw_text: str, display_name: str) -> str:
    """將 12 週總目標原文壓縮成 2-3 句，只抓大方向；短文字直接存原文"""
    if len(raw_text) <= GOAL_SUMMARY_THRESHOLD:
        return raw_text
    prompt = f"""以下是求職群組成員 {display_name} 寫的 12 週目標：

{raw_text}

請用 2-3 句話（約 40-70 字）說明這個人的主要目標與大方向，讓 AI 助手快速了解他在追求什麼。
語言：若原文主要是中文就用繁體中文，英文就用英文。
只輸出 summary 本身，不要加任何前綴。"""
    try:
        response = ai_client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
        )
        return response.text or raw_text[:200]
    except Exception as e:
        print(f"12 週目標 summary 失敗：{e}")
        return raw_text[:200]


def _extract_weekly_goal(raw_text: str) -> str:
    """從討論串最新一則回覆中，只抽出「週目標」部分（≤100 字直接存原文）"""
    if len(raw_text) <= 100:
        return raw_text
    prompt = f"""以下是求職群組成員在目標討論串寫的最新一則更新（可能包含週目標、win、block、ask）：

{raw_text}

請只抽出「這週要做什麼」的部分（週目標、行動計劃），用條列式呈現（- 開頭），每項一句話。
不需要 win、block、ask 的內容。
語言：若原文主要是中文就用繁體中文，英文就用英文。
只輸出條列內容本身，不要加任何前綴或標題。"""
    try:
        response = ai_client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
        )
        return response.text or raw_text[:200]
    except Exception as e:
        print(f"週目標抽取失敗：{e}")
        return raw_text[:200]


def get_member_goal_context(member_id: str) -> dict:
    """取得成員的目標 context（12 週 summary + 當週目標）"""
    result = supabase.table("members") \
        .select("goal_12week_summary, goal_thread_current") \
        .eq("id", member_id) \
        .execute()
    if result.data:
        return {
            "goal_12week": result.data[0].get("goal_12week_summary") or "",
            "goal_thread": result.data[0].get("goal_thread_current") or "",
        }
    return {"goal_12week": "", "goal_thread": ""}


def get_this_week_checkins(member_id: str, member_timezone: str) -> list[str]:
    """取得成員本週（不含今天）的打卡內容"""
    tz = ZoneInfo(member_timezone)
    now = datetime.now(tz)
    # 本週一
    week_start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    today = now.strftime("%Y-%m-%d")

    result = supabase.table("checkins") \
        .select("content, date") \
        .eq("member_id", member_id) \
        .gte("date", week_start) \
        .lt("date", today) \
        .order("date") \
        .execute()
    return [r["content"] for r in result.data]


# ─────────────────────────────────────────
# 指令：!deletecheckin（管理員用，測試時刪除今天打卡）
# ─────────────────────────────────────────
@bot.command(name="deletecheckin")
@commands.has_permissions(administrator=True)
async def deletecheckin(ctx, member: discord.Member = None):
    """【管理員】刪除指定成員今天的打卡紀錄（測試用）。不指定成員則刪自己的。"""
    target = member or ctx.author
    member_result = supabase.table("members") \
        .select("id, timezone") \
        .eq("discord_id", str(target.id)) \
        .execute()

    if not member_result.data:
        await ctx.reply(f"找不到 {target.display_name} 的紀錄。")
        return

    member_row = member_result.data[0]
    tz = ZoneInfo(member_row.get("timezone") or "Asia/Taipei")
    today = datetime.now(tz).strftime("%Y-%m-%d")

    result = supabase.table("checkins") \
        .delete() \
        .eq("member_id", member_row["id"]) \
        .eq("date", today) \
        .execute()

    if result.data:
        # streak 也一起還原（減 1，最低為 0）
        member_data = supabase.table("members") \
            .select("current_streak") \
            .eq("id", member_row["id"]) \
            .execute().data[0]
        new_streak = max(0, (member_data.get("current_streak") or 0) - 1)
        supabase.table("members").update({
            "current_streak": new_streak,
            "last_checkin_date": None if new_streak == 0 else today,
        }).eq("id", member_row["id"]).execute()
        await ctx.reply(f"✅ 已刪除 {target.display_name} 今天（{today}）的打卡紀錄，streak 還原為 {new_streak}。")
    else:
        await ctx.reply(f"{target.display_name} 今天還沒有打卡紀錄。")


# ─────────────────────────────────────────
# 指令：!help
# ─────────────────────────────────────────
@bot.command(name="help")
async def help_command(ctx):
    """列出所有可用指令"""
    is_admin = ctx.author.guild_permissions.administrator

    embed = discord.Embed(title="📖 指令清單", color=0x7c3aed)

    embed.add_field(
        name="一般成員",
        value=(
            "`!stats` — 查看群組整體統計\n"
            "`!leaderboard` / `!lb` — 本週打卡排行榜\n"
            "`!me` — 取得你的個人頁面連結（DM 給你）"
        ),
        inline=False,
    )

    if is_admin:
        embed.add_field(
            name="管理員限定",
            value=(
                "`!deletecheckin [@member]` — 刪除某人今天的打卡（測試用）\n"
                "`!syncgoals` — 掃描 #weekly-goals，補齊所有人的目標資料\n"
                "`!testreport [@member]` — 預覽單人週報\n"
                "`!testreports` — 預覽所有成員週報\n"
                "`!survey [#頻道]` — 啟動結業問卷（Q3 預設發到 #general-chat）"
            ),
            inline=False,
        )

    await ctx.reply(embed=embed)


# 指令：/stats
# ─────────────────────────────────────────
@bot.command(name="stats")
async def stats(ctx, member: discord.Member = None):
    """查看個人打卡統計"""
    target = member or ctx.author
    
    result = supabase.table("members") \
        .select("*, checkins(count)") \
        .eq("discord_id", str(target.id)) \
        .execute()

    if not result.data:
        await ctx.reply("找不到這位成員的紀錄。")
        return

    m = result.data[0]
    total = supabase.table("checkins") \
        .select("id", count="exact") \
        .eq("member_id", m["id"]) \
        .execute().count

    embed = discord.Embed(
        title=f"📊 {target.display_name} 的打卡統計",
        color=0x4f8ef7
    )
    embed.add_field(name="累計打卡", value=f"{total} 天", inline=True)
    embed.add_field(name="目前連續", value=f"{m.get('current_streak', 0)} 天 🔥", inline=True)
    embed.add_field(name="最長連續", value=f"{m.get('longest_streak', 0)} 天", inline=True)
    embed.add_field(name="加入時間", value=m.get("joined_at", "未知")[:10], inline=True)
    embed.set_footer(text=f"{week_label()} / 共 12 週")
    
    await ctx.reply(embed=embed)


# ─────────────────────────────────────────
# 指令：/leaderboard
# ─────────────────────────────────────────
@bot.command(name="leaderboard", aliases=["lb"])
async def leaderboard(ctx):
    """本週打卡排行榜（依「求職 12 週」的活動週次，第 1 週 = 3/9 起算）"""
    cw = current_week()
    if cw == 0:
        await ctx.reply("活動尚未開始（3/9 起為第 1 週），屆時再來查排行榜 💪")
        return

    # 活動第 N 週的日期範圍（台灣時間）：3/9 + (N-1)*7 ～ 3/9 + N*7（不含）
    first_monday = date(2026, 3, 9)
    week_start = first_monday + timedelta(days=(cw - 1) * 7)
    week_end = week_start + timedelta(days=7)
    week_start_str = week_start.strftime("%Y-%m-%d")
    week_end_str = week_end.strftime("%Y-%m-%d")

    result = supabase.rpc("weekly_leaderboard", {
        "week_start": week_start_str,
        "week_end": week_end_str,
    }).execute()

    embed = discord.Embed(
        title=f"🏆 {week_label()}打卡排行榜",
        color=0xf59e0b
    )

    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for i, row in enumerate(result.data[:10]):
        medal = medals[i] if i < 3 else f"{i+1}."
        lines.append(f"{medal} **{row['display_name']}** — {row['checkin_count']} 天")

    embed.description = "\n".join(lines) if lines else "本週還沒有人打卡！"
    embed.set_footer(text=f"統計範圍：{week_start_str}～{week_end_str}（活動第 {cw} 週）")
    await ctx.reply(embed=embed)


# ─────────────────────────────────────────
# 指令：!me（取得個人 Dashboard 連結）
# ─────────────────────────────────────────
async def _safe_reply(ctx, text: str, link: str = None):
    """嘗試在頻道回覆；失敗時改加 reaction，至少讓使用者知道 Bot 有反應。"""
    try:
        await ctx.reply(text)
        return
    except Exception as e:
        print(f"!me 頻道回覆失敗：{e}")
    try:
        await ctx.message.add_reaction("📩")
    except Exception:
        pass


@bot.command(name="me", aliases=["dashboard", "我的"])
async def me(ctx):
    """取得你的專屬 Dashboard 連結，可查看自己的打卡紀錄與排行"""
    # 除錯：一進指令就先反應，確認 Bot 有收到 !me
    print(f"[!me] 指令觸發：{ctx.author} 在 #{getattr(ctx.channel, 'name', ctx.channel)}")
    try:
        await ctx.message.add_reaction("⏳")
    except Exception as e:
        print(f"[!me] 加 reaction 失敗：{e}")

    if not DASHBOARD_URL:
        await _safe_reply(ctx, "管理員尚未設定 Dashboard 網址，無法產生連結。請聯絡管理員。")
        return


    discord_id = str(ctx.author.id)
    link = f"{DASHBOARD_URL}/?discord_id={discord_id}"

    try:
        await ctx.author.send(
            f"👤 **你的專屬 Dashboard 連結**\n\n{link}\n\n"
            "點開後只會看到你自己的打卡紀錄與排行，請勿分享給他人。"
        )
        await _safe_reply(
            ctx,
            "已私訊你的專屬連結給你 👀\n"
            "若沒看到請到 Discord 左側 **私訊** → **訊息請求** 查看（首次傳訊的 Bot 可能會出現在那裡）。"
        )
    except discord.Forbidden:
        await _safe_reply(
            ctx,
            f"無法私訊你（請檢查：伺服器隱私設定是否允許「允許來自伺服器成員的私訊」）。\n\n"
            f"你也可以手動開啟：<{link}>\n\n"
            "⚠️ 請勿分享此連結，他人點開會看到你的打卡紀錄。"
        )
    except Exception as e:
        print(f"!me 私訊失敗：{e}")
        await _safe_reply(ctx, f"私訊時發生錯誤，請直接使用此連結（請勿分享）：\n<{link}>")


# ─────────────────────────────────────────
# 指令：!syncgoals（管理員用，一次性掃描 weekly-goals 歷史）
# ─────────────────────────────────────────
async def _process_goal_message(message: discord.Message):
    """處理 weekly-goals 的主訊息：生成 12 週目標 summary 並存入 DB"""
    author = message.author
    if author.bot:
        return

    member_row = get_or_create_member(str(author.id), str(author), author.display_name)
    member_id = member_row["id"]
    raw_text = message.content.strip()
    if not raw_text:
        return

    summary = await asyncio.to_thread(_summarize_12week_goal, raw_text, author.display_name)
    supabase.table("members").update({
        "goal_12week_summary": summary,
        "goal_message_id": str(message.id),
        "goal_updated_at": datetime.now(TZ).isoformat(),
    }).eq("id", member_id).execute()
    return member_id


async def _process_goal_thread(thread: discord.Thread, member_id: str):
    """掃描討論串所有回覆：
    - goal_thread_current：最新一則的週目標摘要（AI 打卡回覆使用）
    - goal_thread_history：所有回覆原文合併（未來 RAG 使用）
    """
    all_entries = []
    latest_raw = None
    first = True

    async for msg in thread.history(limit=None, oldest_first=True):
        if first:
            first = False
            continue  # 跳過第一則（主計劃已由 _process_goal_message 處理）
        if msg.author.bot:
            continue
        raw = msg.content.strip()
        if not raw:
            continue
        all_entries.append(raw)
        latest_raw = raw  # 最後一則

    if not all_entries:
        return

    # goal_thread_history：所有原文合併
    history = "\n---\n".join(all_entries)

    # goal_thread_current：從最新一則抽出週目標
    current = await asyncio.to_thread(_extract_weekly_goal, latest_raw) if latest_raw else ""

    supabase.table("members").update({
        "goal_thread_current": current,
        "goal_thread_history": history,
        "goal_updated_at": datetime.now(TZ).isoformat(),
    }).eq("id", member_id).execute()


@bot.command(name="syncgoals")
@commands.has_permissions(administrator=True)
async def syncgoals(ctx):
    """【管理員】一次性掃描 weekly-goals channel，將所有人的目標 summary 存入 DB"""
    goals_channel = discord.utils.get(ctx.guild.channels, name=GOAL_CHANNEL_NAME)
    if not goals_channel:
        await ctx.reply(f"找不到 #{GOAL_CHANNEL_NAME} 頻道。")
        return

    await ctx.reply(f"開始掃描 #{GOAL_CHANNEL_NAME}，請稍候...")
    count = 0

    # Forum 頻道：每個帖子（post）是一個 Thread，第一則訊息是主目標
    threads = list(goals_channel.threads)
    # 也抓取已封存的帖子
    async for thread in goals_channel.archived_threads(limit=None):
        threads.append(thread)

    for thread in threads:
        # 取得帖子的第一則訊息（即主目標訊息）
        messages = [msg async for msg in thread.history(limit=None, oldest_first=True)]
        if not messages:
            continue

        first_msg = messages[0]
        if first_msg.author.bot:
            continue

        member_id = await _process_goal_message(first_msg)
        if not member_id:
            continue

        # 其餘訊息為討論回覆
        if len(messages) > 1:
            await _process_goal_thread(thread, member_id)

        count += 1

    await ctx.reply(f"✅ 完成！已同步 {count} 位成員的目標資料。")


# ─────────────────────────────────────────
# 週報功能
# ─────────────────────────────────────────
def generate_weekly_report(display_name: str, goal_12week: str, goal_thread: str,
                            checkins: list[dict]) -> str:
    """Calls Gemini to produce a personalised weekly DM report."""
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


class ReportApprovalView(discord.ui.View):
    """Approval buttons posted to admin channel before DM-ing the member."""

    def __init__(self, discord_id: str, report_text: str, display_name: str, date_range: str = ""):
        super().__init__(timeout=86400)  # 24-hour window
        self.discord_id = discord_id
        self.report_text = report_text
        self.display_name = display_name
        self.date_range = date_range

    @discord.ui.button(label="✅ 發送 DM", style=discord.ButtonStyle.success)
    async def send_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            member = (interaction.guild.get_member(int(self.discord_id))
                      or await interaction.guild.fetch_member(int(self.discord_id)))
            header = f"📬 **你的本週個人回顧 / Your Weekly Report**"
            if self.date_range:
                header += f"（{self.date_range}）"
            await member.send(f"{header}\n\n{self.report_text}")
            for child in self.children:
                child.disabled = True
            button.label = "✅ 已發送"
            await interaction.response.edit_message(view=self)
        except discord.Forbidden:
            await interaction.response.send_message("❌ 對方關閉了 DM", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ 發送失敗: {e}", ephemeral=True)

    @discord.ui.button(label="🚫 跳過", style=discord.ButtonStyle.secondary)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)


async def post_report_preview(member_row: dict, guild: discord.Guild,
                               channel: discord.TextChannel,
                               force: bool = False) -> bool:
    """Generate report and post a preview embed with Send/Skip buttons to the given channel."""
    discord_id = member_row.get("discord_id")
    if not discord_id:
        return False

    tz_str = member_row.get("timezone") or "Asia/Taipei"
    now_local = datetime.now(ZoneInfo(tz_str))

    if not force and not (now_local.weekday() == 0 and now_local.hour == 20):
        return False

    # Most recently completed Mon–Sun week, works regardless of what day this runs
    today_date = now_local.date()
    last_sunday = today_date - timedelta(days=today_date.weekday() + 1)
    last_monday = last_sunday - timedelta(days=6)
    checkins_res = supabase.table("checkins") \
        .select("date, content, completed_goals") \
        .eq("member_id", member_row["id"]) \
        .gte("date", last_monday.strftime("%Y-%m-%d")) \
        .lte("date", last_sunday.strftime("%Y-%m-%d")) \
        .order("date") \
        .execute()
    checkins = checkins_res.data or []

    has_any_goal = bool(member_row.get("goal_12week_summary") or member_row.get("goal_thread_current"))
    if not has_any_goal or len(checkins) == 0:
        return False

    has_weekly_goal = bool(member_row.get("goal_thread_current"))
    if not force and (len(checkins) < 3 or not has_weekly_goal):
        return False

    try:
        report_text = await asyncio.to_thread(
            generate_weekly_report,
            member_row.get("display_name", "Member"),
            member_row.get("goal_12week_summary", ""),
            member_row.get("goal_thread_current", ""),
            checkins,
        )
    except Exception as e:
        print(f"週報 AI 生成失敗 ({discord_id}): {e}")
        return False

    date_range = f"{last_monday.strftime('%m/%d')} – {last_sunday.strftime('%m/%d')}"

    embed = discord.Embed(
        title=f"📬 週報預覽 — {member_row.get('display_name', discord_id)}",
        description=report_text,
        color=0x7c3aed,
    )
    embed.set_footer(text=f"{date_range} · 打卡 {len(checkins)} 次 · 確認後點「發送 DM」")

    view = ReportApprovalView(discord_id, report_text, member_row.get("display_name", ""), date_range)
    await channel.send(embed=embed, view=view)
    return True


@tasks.loop(hours=1)
async def weekly_report():
    """Every Monday 8pm (per-timezone) posts report previews to admin channel for approval."""
    now_utc = datetime.now(timezone.utc)

    all_members = supabase.table("members") \
        .select("id, discord_id, display_name, timezone, goal_12week_summary, goal_thread_current") \
        .execute().data

    for guild in bot.guilds:
        admin_ch = discord.utils.get(guild.channels, name=ADMIN_CHANNEL_NAME)
        if not admin_ch:
            continue
        for m in all_members:
            tz_str = m.get("timezone") or "Asia/Taipei"
            local = now_utc.astimezone(ZoneInfo(tz_str))
            if local.weekday() == 0 and local.hour == 20:
                await post_report_preview(m, guild, admin_ch)


@bot.command(name="testreport")
@commands.has_permissions(administrator=True)
async def testreport(ctx, member: discord.Member = None):
    """[Admin] Preview a weekly report for one member (default: yourself)."""
    target = member or ctx.author
    discord_id = str(target.id)

    member_res = supabase.table("members") \
        .select("id, discord_id, display_name, timezone, goal_12week_summary, goal_thread_current") \
        .eq("discord_id", discord_id) \
        .execute()

    if not member_res.data:
        await ctx.reply(f"找不到成員 {target.display_name} 的資料。")
        return

    await ctx.reply(f"正在生成 {target.display_name} 的週報預覽，請稍候...")
    sent = await post_report_preview(member_res.data[0], ctx.guild, ctx.channel, force=True)
    if not sent:
        await ctx.reply("❌ 生成失敗，請查看 bot log。")


@bot.command(name="testreports")
@commands.has_permissions(administrator=True)
async def testreports(ctx):
    """[Admin] Preview weekly reports for ALL members — simulates the Monday batch run."""
    all_members = await asyncio.to_thread(
        lambda: supabase.table("members")
        .select("id, discord_id, display_name, timezone, goal_12week_summary, goal_thread_current")
        .execute().data
    )

    if not all_members:
        await ctx.reply("找不到任何成員資料。")
        return

    await ctx.reply(f"正在為 {len(all_members)} 位成員生成週報預覽，請稍候⋯⋯")
    success, skipped = 0, 0
    for m in all_members:
        sent = await post_report_preview(m, ctx.guild, ctx.channel, force=True)
        if sent:
            success += 1
        else:
            skipped += 1

    await ctx.reply(f"✅ 完成！產生 {success} 份預覽，跳過 {skipped} 位（無資料或生成失敗）。")


# ─────────────────────────────────────────
# 問卷功能
# ─────────────────────────────────────────
_pending_surveys: dict[str, dict] = {}
# {discord_id: {"q1": str|None, "member_name": str, "admin_channel_id": int}}


class SurveyQ2View(discord.ui.View):
    def __init__(self, discord_id: str, q1_answer: str, admin_channel_id: int, member_name: str):
        super().__init__(timeout=86400 * 3)  # 3 days
        self.discord_id = discord_id
        self.q1_answer = q1_answer
        self.admin_channel_id = admin_channel_id
        self.member_name = member_name

    async def _submit(self, interaction: discord.Interaction, choice: str):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        admin_ch = bot.get_channel(self.admin_channel_id)
        if admin_ch:
            embed = discord.Embed(
                title=f"📋 問卷回覆 — {self.member_name}",
                color=0x5865f2,
            )
            embed.add_field(
                name="Q1 這三個月對你幫助最大的是什麼？",
                value=self.q1_answer or "(未填)",
                inline=False,
            )
            embed.add_field(name="Q2 六月之後你的狀態？", value=choice, inline=False)
            await admin_ch.send(embed=embed)

        await interaction.followup.send("✅ 謝謝你的回覆！已送出。", ephemeral=True)
        _pending_surveys.pop(self.discord_id, None)

    @discord.ui.button(label="A. 還是在積極衝刺目標", style=discord.ButtonStyle.primary, row=0)
    async def choice_a(self, interaction, button):
        await self._submit(interaction, "A. 還是在積極衝刺目標")

    @discord.ui.button(label="B. 進入比較緩的節奏", style=discord.ButtonStyle.secondary, row=1)
    async def choice_b(self, interaction, button):
        await self._submit(interaction, "B. 進入比較緩的節奏")

    @discord.ui.button(label="C. 還不確定", style=discord.ButtonStyle.secondary, row=2)
    async def choice_c(self, interaction, button):
        await self._submit(interaction, "C. 還不確定")

    @discord.ui.button(label="D. 可能會暫停一陣子", style=discord.ButtonStyle.danger, row=3)
    async def choice_d(self, interaction, button):
        await self._submit(interaction, "D. 可能會暫停一陣子")


@bot.command(name="survey")
@commands.has_permissions(administrator=True)
async def survey(ctx, public_channel: discord.TextChannel = None):
    """[Admin] 啟動結業問卷：私訊所有成員 Q1+Q2，並在指定公開頻道發 Q3。
    用法：!survey 或 !survey #頻道名稱"""
    q3_channel = public_channel or discord.utils.get(ctx.guild.channels, name="general-chat") or ctx.channel
    admin_ch = discord.utils.get(ctx.guild.channels, name=ADMIN_CHANNEL_NAME)
    if not admin_ch:
        await ctx.reply(f"找不到 #{ADMIN_CHANNEL_NAME} 頻道，請先建立它。")
        return

    all_members = await asyncio.to_thread(
        lambda: supabase.table("members")
        .select("id, discord_id, display_name")
        .execute().data
    )

    if not all_members:
        await ctx.reply("找不到任何成員資料。")
        return

    await ctx.reply(f"正在發送問卷給 {len(all_members)} 位成員⋯⋯")

    sent, failed = 0, 0
    for m in all_members:
        discord_id = m.get("discord_id")
        if not discord_id:
            failed += 1
            continue
        try:
            member = ctx.guild.get_member(int(discord_id)) or \
                     await ctx.guild.fetch_member(int(discord_id))
            _pending_surveys[discord_id] = {
                "q1": None,
                "member_name": member.display_name,
                "admin_channel_id": admin_ch.id,
            }
            await member.send(
                "👋 嗨！這是求職群組的結業問卷，你的回答只有管理員看得到。\n\n"
                "**問題一：這三個月對你幫助最大的是什麼？**\n"
                "直接在這裡回覆就好 💬"
            )
            sent += 1
        except discord.Forbidden:
            failed += 1
            print(f"問卷 DM 被拒絕：{discord_id}")
        except Exception as e:
            failed += 1
            print(f"問卷發送失敗 ({discord_id}): {e}")

    await q3_channel.send(
        "💬 **結業問卷 — 公開討論**\n\n"
        "**問題三：接下來你最想努力的方向是什麼？**\n"
        "歡迎在下面留言分享，讓大家互相認識彼此的下一步 🌱"
    )

    await ctx.reply(
        f"✅ 問卷發送完成！成功 {sent} 人，失敗 {failed} 人。\n"
        f"成員的 Q1+Q2 回覆會統一傳到 #{ADMIN_CHANNEL_NAME}，Q3 已發到 #{q3_channel.name}。"
    )


# ─────────────────────────────────────────
# 事件：啟動
# ─────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅ Bot 上線：{bot.user}")
    weekly_summary.start()
    daily_reminder.start()
    weekly_report.start()


# ─────────────────────────────────────────
# 事件：weekly-goals 有新訊息或編輯時自動同步
# ─────────────────────────────────────────
@bot.event
async def on_message(message: discord.Message):
    # 忽略 bot 自己的訊息
    if message.author.bot:
        return

    # 問卷 Q1 DM 回覆
    if isinstance(message.channel, discord.DMChannel):
        discord_id = str(message.author.id)
        survey_state = _pending_surveys.get(discord_id)
        if survey_state and survey_state["q1"] is None:
            survey_state["q1"] = message.content.strip()
            await message.channel.send(
                "謝謝你的分享！✨\n\n"
                "**問題二：六月之後你的狀態大概會是什麼？**\n"
                "請點選下方按鈕：",
                view=SurveyQ2View(
                    discord_id,
                    survey_state["q1"],
                    survey_state["admin_channel_id"],
                    survey_state["member_name"],
                ),
            )
        return

    # weekly-goals（Forum 頻道）：新帖子第一則訊息 = 主目標；ID 與 thread ID 相同
    if (
        isinstance(message.channel, discord.Thread)
        and message.channel.parent
        and message.channel.parent.name == GOAL_CHANNEL_NAME
        and message.id == message.channel.id
    ):
        try:
            await _process_goal_message(message)
        except Exception as e:
            print(f"weekly-goals 主帖同步失敗：{e}")
        return

    # weekly-goals 討論串：帖子內的後續回覆
    if (
        isinstance(message.channel, discord.Thread)
        and message.channel.parent
        and message.channel.parent.name == GOAL_CHANNEL_NAME
    ):
        try:
            # Forum 頻道的討論串，owner_id 就是發起帖子的人
            owner_id = message.channel.owner_id
            if owner_id:
                owner = message.guild.get_member(owner_id) or await message.guild.fetch_member(owner_id)
                member_row = get_or_create_member(
                    str(owner.id), str(owner), owner.display_name
                )
                await _process_goal_thread(message.channel, member_row["id"])
        except Exception as e:
            print(f"weekly-goals 討論串同步失敗：{e}")
        return

    # ── 以下是原本的 on_message 邏輯 ──

    # 如果 Tag 了機器人：若內容是指令（! 開頭）先執行指令，否則才當聊天
    if bot.user in message.mentions:
        content = message.content.replace(f'<@{bot.user.id}>', '').strip()
        if content and content.startswith("!"):
            await bot.process_commands(message)
            return
        if content:
            async with message.channel.typing():
                try:
                    is_english = _is_mainly_english(content)
                    if is_english:
                        lang_instruction = "使用者這次主要是用英文與你說話，因此你最終輸出的回覆必須完全以英文書寫，不要使用中文，語氣自然、像母語人士。"
                    else:
                        lang_instruction = "使用者這次主要是用繁體中文與你說話，因此你最終輸出的回覆必須完全以繁體中文書寫，不要使用英文，語氣自然、像朋友聊天。"

                    correction_note = ""
                    if ENABLE_ENGLISH_CORRECTION and is_english:
                        correction_note = "若使用者用英文且句子有明顯中式或不自然表達，可於回覆末尾用一句英文示範更自然的說法（可選），保留原本語氣，不用糾正常見縮寫。"

                    prompt = f"你是一個溫暖、真誠的求職群組陪伴助手。成員 {message.author.display_name} 在群組裡對你說：\n「{content}」\n\n{lang_instruction} {correction_note}\n請用友善、像朋友般的語氣給予簡短回覆（控制在 30-60 字以內），不要加太多 Emoji。"
                    response = await asyncio.to_thread(lambda: ai_client.models.generate_content(
                        model="gemini-2.5-flash-lite",
                        contents=prompt
                    ).text)
                    await message.reply(response)
                except Exception as e:
                    print(f"聊天回覆失敗：{e}")
        return

    # 討論串訊息不觸發打卡（有人在別人打卡底下回覆時不應記錄）
    # 用 isinstance 之外也檢查 channel type，避免 Thread 未 cache 時回傳 PartialMessageable 而漏判
    _thread_types = {
        discord.ChannelType.public_thread,
        discord.ChannelType.private_thread,
        discord.ChannelType.news_thread,
    }
    is_thread = isinstance(message.channel, discord.Thread) or \
                getattr(message.channel, 'type', None) in _thread_types
    if is_thread:
        await bot.process_commands(message)
        return

    # 回覆他人訊息不觸發打卡（用 Reply 按鈕留言給別人時不應記錄）
    if message.reference is not None:
        await bot.process_commands(message)
        return

    # 只處理打卡頻道
    if message.channel.name not in CHECKIN_CHANNELS:
        await bot.process_commands(message)
        return

    # 內容太短（少於 2 個字）直接忽略，不作為打卡
    content = message.content.strip()
    if len(content) < 2:
        await bot.process_commands(message)
        return

    author = message.author
    member_row = get_or_create_member(
        str(author.id),
        str(author),
        author.display_name
    )
    member_id = member_row["id"]
    member_tz = member_row.get("timezone") or "Asia/Taipei"

    # 已打卡：不重複記錄，但給個提示
    if already_checked_in(member_id, member_tz):
        try:
            await message.add_reaction("✅")
        except Exception:
            pass
        return

    # 儲存打卡
    checkin = save_checkin(
        member_id=member_id,
        content=content,
        channel_id=str(message.channel.id),
        message_id=str(message.id),
        member_timezone=member_tz,
    )

    # 更新連續天數（用成員當地昨天／今天，避免時區算錯）
    streak = update_streak(member_id, member_tz, checkin["date"])

    # 確認 reaction
    try:
        await message.add_reaction("✅")
    except Exception:
        pass

    # 產生 AI 回覆（非同步，避免卡住）
    async with message.channel.typing():
        try:
            goal_ctx = await asyncio.to_thread(get_member_goal_context, member_id)
            week_checkins = await asyncio.to_thread(get_this_week_checkins, member_id, member_tz)
            week_number = week_number_for_member(member_tz)

            # Node 1: analyze check-in
            analysis = await asyncio.to_thread(
                _analyze_checkin,
                content,
                author.display_name,
                goal_ctx["goal_12week"],
                goal_ctx["goal_thread"],
                week_checkins,
                week_number,
            )

            # Node 2: route to strategy
            strategy = _route(analysis, week_number)
            print(
                f"[agent] {author.display_name} → {strategy} | "
                f"state={analysis.get('emotional_state')} "
                f"block={analysis.get('block_type')} "
                f"mode={analysis.get('mode')}"
            )

            # Store completed_goals and goal_coverage to the checkin DB row
            try:
                supabase.table("checkins").update({
                    "completed_goals": analysis.get("completed_goals", []),
                    "goal_coverage": analysis.get("goal_coverage", "none"),
                }).eq("id", checkin["id"]).execute()
            except Exception as db_e:
                print(f"更新 completed_goals 失敗：{db_e}")

            # Node 3: generate reply
            is_english = _is_mainly_english(content)
            reply = await asyncio.to_thread(
                _generate_reply,
                strategy,
                analysis,
                content,
                author.display_name,
                streak,
                goal_ctx["goal_12week"],
                goal_ctx["goal_thread"],
                is_english,
            )
            save_ai_reply(checkin["id"], reply)

            # 加入連續打卡里程碑（個人頁連結改由 !me 私訊取得，不在公開頻道揭露）
            milestone = ""
            if streak in (3, 7, 14, 21, 30):
                milestone = f"\n\n🔥 **{streak} 天連續打卡里程碑！** 你做到了！"
            elif streak > 1:
                milestone = f"\n*（連續第 {streak} 天 🔥）*"

            await message.reply(reply + milestone, mention_author=False)

        except Exception as e:
            print(f"AI 回覆失敗：{e}")
            try:
                await message.add_reaction("✅")
            except Exception:
                pass

    await bot.process_commands(message)


# ─────────────────────────────────────────
# 事件：weekly-goals 訊息被編輯時自動更新
# ─────────────────────────────────────────
@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    # 忽略 bot 自己的訊息
    if after.author.bot:
        return

    # weekly-goals 主帖編輯（Forum 帖子第一則訊息）→ 重新生成 12 週目標 summary
    if (
        isinstance(after.channel, discord.Thread)
        and after.channel.parent
        and after.channel.parent.name == GOAL_CHANNEL_NAME
        and after.id == after.channel.id
    ):
        try:
            await _process_goal_message(after)
        except Exception as e:
            print(f"weekly-goals 主帖編輯同步失敗：{e}")
        return

    # weekly-goals 討論串編輯 → 重新掃描整條討論串
    if (
        isinstance(after.channel, discord.Thread)
        and after.channel.parent
        and after.channel.parent.name == GOAL_CHANNEL_NAME
    ):
        try:
            owner_id = after.channel.owner_id
            if owner_id:
                owner = after.guild.get_member(owner_id) or await after.guild.fetch_member(owner_id)
                member_row = get_or_create_member(
                    str(owner.id), str(owner), owner.display_name
                )
                await _process_goal_thread(after.channel, member_row["id"])
        except Exception as e:
            print(f"weekly-goals 討論串編輯同步失敗：{e}")
        return

    # 只處理打卡頻道的編輯
    if after.channel.name not in CHECKIN_CHANNELS:
        return

    new_content = after.content.strip()
    # 編輯後如果變得太短，就不要覆蓋原本內容
    if len(new_content) < 2:
        return

    try:
        # 透過 message_id + channel_id 找到對應的打卡紀錄
        result = (
            supabase.table("checkins")
            .select("id")
            .eq("message_id", str(after.id))
            .eq("channel_id", str(after.channel.id))
            .execute()
        )

        if not result.data:
            # 很可能是當時那則訊息沒被當成打卡（例如已經打過卡）
            return

        checkin_id = result.data[0]["id"]
        supabase.table("checkins").update({"content": new_content}).eq("id", checkin_id).execute()
    except Exception as e:
        print(f"更新打卡內容失敗（on_message_edit）：{e}")


# ─────────────────────────────────────────
# 定時任務：每日提醒
# 每小時跑一次，對「現在剛好是當地晚上 9 點」的成員發提醒
# ─────────────────────────────────────────
@tasks.loop(hours=1)
async def daily_reminder():
    now_utc = datetime.now(timezone.utc)

    # 取所有成員（含時區）
    all_members = supabase.table("members") \
        .select("id, discord_id, display_name, timezone") \
        .execute().data

    # 篩出「現在剛好是當地 21:xx」的成員（排除助教/觀察者）
    members_to_check = [
        m for m in all_members
        if now_utc.astimezone(ZoneInfo(m.get("timezone") or "Asia/Taipei")).hour == 21
        and str(m.get("discord_id")) not in REMINDER_EXCLUDED
    ]

    if not members_to_check:
        return  # 這個小時沒有任何時區到晚上 9 點，直接跳過

    # 查這些成員裡，今天（各自本地時間）還沒打卡的人
    missing = []
    for m in members_to_check:
        local_today = now_utc.astimezone(
            ZoneInfo(m.get("timezone") or "Asia/Taipei")
        ).strftime("%Y-%m-%d")

        already = supabase.table("checkins") \
            .select("id") \
            .eq("member_id", m["id"]) \
            .eq("date", local_today) \
            .execute().data

        if not already:
            missing.append(m)

    if not missing:
        return

    # 發提醒
    for guild in bot.guilds:
        channel = discord.utils.get(guild.channels, name="daily-micro-action")
        if not channel:
            continue

        if len(missing) <= 5:
            mentions = " ".join(f"<@{m['discord_id']}>" for m in missing)
            await channel.send(
                f"👋 還沒打卡的朋友們：{mentions}\n"
                f"今天不管發生什麼，哪怕只是一句話，來這裡記錄一下吧 🌙"
            )
        else:
            await channel.send(
                f"👋 還有 **{len(missing)} 位**朋友今天還沒打卡，\n"
                f"不管今天過得如何，一句話就夠了 🌙"
            )


# ─────────────────────────────────────────
# 定時任務：每週日總結
# ─────────────────────────────────────────
@tasks.loop(hours=24)
async def weekly_summary():
    now = datetime.now(TZ)  # 台灣時間 (UTC+8)
    if now.weekday() != 6 or now.hour != 22:  # 週日 台灣晚上 10 點（美東早上 10 點）
        return
    if current_week() == 0:  # 尚未開始（3/9 前）不發週總結
        return

    for guild in bot.guilds:
        admin_ch = discord.utils.get(guild.channels, name=ADMIN_CHANNEL_NAME)
        announcement_ch = discord.utils.get(guild.channels, name="announcement")
        if not announcement_ch:
            continue

        week = current_week()
        week_start = (now - timedelta(days=6)).strftime("%Y-%m-%d")

        # 本週所有打卡內容
        rows = supabase.table("checkins") \
            .select("content, members(display_name)") \
            .gte("date", week_start) \
            .execute().data

        if not rows:
            continue

        # 統計
        total_checkins = len(rows)
        unique_members = len({r["members"]["display_name"] for r in rows})

        # 用 AI 生成週總結
        contents_sample = "\n".join(
            f"- {r['members']['display_name']}: {r['content'][:80]}"
            for r in rows[:30]  # 最多 30 筆避免 token 過多
        )

        summary_prompt = f"""以下是一個求職群組第 {week} 週的打卡紀錄（共 {total_checkins} 則）：

{contents_sample}

請根據上述打卡內容的主要使用語言來寫週總結：若多數為英文則用英文，若多數為繁體中文則用繁體中文。長度約 150 字，包含：
1. 這週群組整體的氛圍和能量
2. 觀察到的共同挑戰或突破
3. 給下週的一句鼓勵

語氣溫暖，像是一個很懂大家的朋友在說話。"""

        try:
            summary = await asyncio.to_thread(lambda: ai_client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=summary_prompt
            ).text)

            embed = discord.Embed(
                title=f"📖 第 {week} 週回顧",
                description=summary,
                color=0x7c3aed
            )
            embed.add_field(name="本週打卡次數", value=str(total_checkins), inline=True)
            embed.add_field(name="活躍成員", value=f"{unique_members} 人", inline=True)
            embed.set_footer(text=f"第 {week}/12 週完成 ✨")

            await announcement_ch.send(embed=embed)

        except Exception as e:
            print(f"週總結失敗：{e}")


# ─────────────────────────────────────────
# 啟動（遇 429 速率限制時等待後重試，避免 Railway 重啟循環）
# ─────────────────────────────────────────
def run_bot():
    max_retries = 5
    wait_seconds = 60
    for attempt in range(max_retries):
        try:
            bot.run(DISCORD_TOKEN)
            return
        except discord.errors.HTTPException as e:
            if e.status == 429 and attempt < max_retries - 1:
                print(f"Discord 429 速率限制，{wait_seconds} 秒後重試 ({attempt + 1}/{max_retries})...")
                time.sleep(wait_seconds)
            else:
                raise


run_bot()
