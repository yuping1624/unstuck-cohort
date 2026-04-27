"""
求職 12 週 Discord Bot
功能：打卡收集、AI 回覆、連續天數追蹤、週提醒
"""

import os
import re
import asyncio
import time
from datetime import date, datetime, timedelta, timezone
import discord
from discord.ext import commands, tasks
from supabase import create_client, Client
from google import genai
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

bot = commands.Bot(command_prefix="!", intents=intents)


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


def get_ai_reply(
    content: str,
    display_name: str,
    streak: int,
    goal_12week: str = "",
    goal_thread: str = "",
    week_checkins: list = None,
) -> str:
    """呼叫 Gemini 產生個人化回覆；失敗時回傳友善預設訊息"""
    streak_context = f"（今天是他連續第 {streak} 天打卡）" if streak > 1 else "（今天是他第一次或重新開始打卡）"

    is_english = _is_mainly_english(content)

    if is_english:
        lang_instruction = """使用者這次主要是用英文打卡，因此你最終輸出的回覆必須「完全以英文書寫」，不要使用中文。語氣自然、像母語人士，允許口語化與日常對話用語。"""
    else:
        lang_instruction = """使用者這次主要是用繁體中文打卡，因此你最終輸出的回覆必須「完全以繁體中文書寫」，不要使用英文。語氣自然、口語化，像朋友聊天。"""

    correction_instruction = ""
    if ENABLE_ENGLISH_CORRECTION and is_english:
        correction_instruction = """
若使用者的英文帶有明顯「中式英文」或不太自然的表達，請在回覆的最後，用 1 句簡短的英文示範更自然、道地的說法，例如：'P.S. A more natural way to say this is: ...'。請優先保留原本的語氣與情緒，不要改成很正式的文章；對於母語人士常用的縮寫或口語（例如 gonna, wanna, btw 等）通常不必更正，除非會讓意思變得不清楚。"""

    # 組裝記憶 context（只在有資料時才加入）
    memory_context = ""
    if goal_12week:
        memory_context += f"\n【12 週目標】{goal_12week}"
    if goal_thread:
        memory_context += f"\n【近期目標與進展紀錄】\n{goal_thread}"
    if week_checkins:
        checkins_text = "\n".join(f"- {c}" for c in week_checkins)
        memory_context += f"\n【本週其他打卡紀錄】\n{checkins_text}"

    memory_section = ""
    if memory_context:
        memory_section = f"\n\n以下是關於這位成員的背景資訊，請參考後給出更有針對性的回覆：{memory_context}\n"

    prompt = f"""你是一個溫暖、真誠的目標達成群組助手，負責回覆成員的每日打卡。群組成員各自有不同的 12 週目標（有人求職、有人做 side project、有人學習新技能等），請根據每位成員的個人目標給予回覆，不要預設所有人都在求職。

成員：{display_name} {streak_context}
今天的打卡內容：{content}
{memory_section}
{lang_instruction}
其他要求：
1. 回覆長度根據打卡內容調整：打卡內容簡短（1-2 句）就回 2 句；打卡內容豐富（3 句以上或超過 80 字）必須回 3-4 句，針對他提到的具體細節給予回饋，絕對不能只用一句話帶過，但不要超過 5 句
2. 針對他寫的內容給出真實共鳴，不要泛泛鼓勵，例如不要說「加油」、「繼續努力」這種空洞的話
3. 如果有情緒低落的跡象，給予溫暖支持而非空洞打氣；若【本週其他打卡紀錄】裡有具體的進展或克服困難的內容，可以提及來鼓勵他，但不能用【12 週目標】或【近期目標與進展紀錄】的內容來假裝是「你之前做過的事」
4. 如果有具體進展（面試、Offer等），真心恭喜
5. 若今天打卡內容和 12 週目標無關（例如休息、身體不舒服、考試），必須在回覆最後加上一句明天可以做的超小具體行動，直接從【當週目標】的行動項目裡挑一件最小的來建議（例如目標是投履歷就說「明天投一間就好」、目標是 coffee chat 就說「明天傳一封訊息約一個人」），不要自己推測或發揮，不要複述目標原文，語氣像朋友隨口一提，不要說教
6. 結尾可以加 1 個 emoji，不要過多
7. 語氣像朋友，不要像機器人或客服
8. 若有背景資訊，自然地融入回覆，不要生硬地逐條列舉
9. 不要說「我們之前聊過」、「你之前提過」、「你說過」這類假裝有過去對話的語句，直接自然帶入就好
{correction_instruction}

只輸出回覆內容，不要加任何前綴。"""

    try:
        response = ai_client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt,
        )
        # 部分情況可能不會有 text，做個保險
        return response.text or "今天已經成功打卡了！你的努力已經被記錄下來 🙌"
    except Exception as e:
        # 印在終端機方便你 debug
        print(f"AI 回覆失敗（get_ai_reply）：{e}")
        # 回傳一則友善的預設訊息，避免完全沒有回覆
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
        f"- [{c['date']}] {c['content'][:120]}" for c in checkins
    ) or "(no check-ins this week)"

    prompt = f"""You are a brutally honest but deeply caring career coach for a 12-week job-search accountability group.

Member: {display_name}
12-week goal: {goal_12week or '(not set)'}
This week's focus: {goal_thread or '(not set)'}
Check-ins this week:
{checkin_lines}

═══════════════════════════════════
STEP 1 — INTERNAL DIAGNOSIS (do NOT output anything from this step):
═══════════════════════════════════

A. Identify the ONE specific block this member faces. Be precise:
   ✗ "procrastination"  →  ✓ "hasn't sent any applications despite planning to for two weeks"
   ✗ "anxiety"          →  ✓ "avoids reaching out to contacts to escape fear of seeming desperate"

B. Choose the ONE psychological lens that best explains WHY this block persists:
   • Cognitive Overload — too many competing priorities; working memory is full, execution collapses
   • Launch Friction — initiation cost feels disproportionately high relative to the perceived reward
   • Learned Helplessness (Seligman) — repeated setbacks caused withdrawal; "nothing I do matters"
   • Fear of Evaluation — avoids action to avoid being judged or rejected (approach-avoidance conflict)
   • Identity Gap (James Clear) — the target role doesn't feel like "who I am yet"; behaviour and identity misaligned
   • Meaning Deficit (Frankl / Logotherapy) — disconnected from the deeper "why"; job search feels hollow
   • Progress Blindness (Amabile) — real incremental progress exists but the member cannot perceive it
   • Execution Fragmentation — right intention, but no reliable time/environment system to convert intent to action
   • Stoic Control Boundary — energy spent on outcomes (offer, response) rather than process (applications sent, prep quality)
   • WOOP gap (Oettingen) — visualising success without mentally contrasting the obstacle → false sense of progress

C. Decide output language: Traditional Chinese if check-ins are mostly Chinese; English if mostly English.

═══════════════════════════════════
STEP 2 — OUTPUT (write in the language from Step 1C):
═══════════════════════════════════

Use EXACTLY these three headers, no greeting, no sign-off:

🎯 進度快照 / Snapshot:
<ONE sentence. Ultra-brief factual recap. No praise. Member already knows what they did — don't re-narrate it.>

💡 洞見 / Insight:
<2-3 sentences. Name the specific block from Step 1A. Apply the lens from Step 1B to explain the psychology behind it — reference the framework concept by name if helpful (e.g. "launch friction", "learned helplessness", "identity gap"). Be direct and honest. Zero flattery. The member should feel: "this AI sees my real obstacle, not just my surface behaviour".>

🚀 微行動 / Micro-action:
<ONE Implementation Intention: "When [specific trigger / time / situation], I will [tiny specific behaviour]."
Constraints: (1) Starting it takes ≤2 minutes. (2) It must be MORE specific and smaller than anything the member already planned. (3) Its sole purpose is to dissolve the identified block's launch friction — not to complete a project.>

Total: 180-230 Chinese characters OR 150-190 English words."""

    return ai_client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt
    ).text.strip()


class ReportApprovalView(discord.ui.View):
    """Approval buttons posted to admin channel before DM-ing the member."""

    def __init__(self, discord_id: str, report_text: str, display_name: str):
        super().__init__(timeout=86400)  # 24-hour window
        self.discord_id = discord_id
        self.report_text = report_text
        self.display_name = display_name

    @discord.ui.button(label="✅ 發送 DM", style=discord.ButtonStyle.success)
    async def send_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            member = (interaction.guild.get_member(int(self.discord_id))
                      or await interaction.guild.fetch_member(int(self.discord_id)))
            await member.send(
                f"📬 **你的本週個人回顧 / Your Weekly Report**\n\n{self.report_text}"
            )
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

    week_ago = (now_local - timedelta(days=7)).strftime("%Y-%m-%d")
    checkins_res = supabase.table("checkins") \
        .select("date, content") \
        .eq("member_id", member_row["id"]) \
        .gte("date", week_ago) \
        .order("date") \
        .execute()
    checkins = checkins_res.data or []

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

    embed = discord.Embed(
        title=f"📬 週報預覽 — {member_row.get('display_name', discord_id)}",
        description=report_text,
        color=0x7c3aed,
    )
    embed.set_footer(text=f"本週打卡 {len(checkins)} 次 · 確認後點「發送 DM」")

    view = ReportApprovalView(discord_id, report_text, member_row.get("display_name", ""))
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
    """[Admin] Preview a weekly report with Send/Skip buttons before it goes to the member."""
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
    print(f"[debug] channel={message.channel!r} type={getattr(message.channel,'type',None)} is_thread={is_thread}")
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
        await message.add_reaction("✅")
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
    await message.add_reaction("✅")

    # 產生 AI 回覆（非同步，避免卡住）
    async with message.channel.typing():
        try:
            goal_ctx = await asyncio.to_thread(get_member_goal_context, member_id)
            week_checkins = await asyncio.to_thread(get_this_week_checkins, member_id, member_tz)
            reply = await asyncio.to_thread(
                get_ai_reply,
                content,
                author.display_name,
                streak,
                goal_ctx["goal_12week"],
                goal_ctx["goal_thread"],
                week_checkins,
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
            await message.add_reaction("✅")

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

    # 篩出「現在剛好是當地 21:xx」的成員
    members_to_check = [
        m for m in all_members
        if now_utc.astimezone(ZoneInfo(m.get("timezone") or "Asia/Taipei")).hour == 21
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
        channel = discord.utils.get(guild.channels, name="每日打卡")
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
