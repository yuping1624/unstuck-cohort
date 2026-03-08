"""
一次性腳本：依 checkins 表重算所有成員的 current_streak、longest_streak。
若資料庫裡 streak 與實際打卡數不一致（例如只打一筆卻顯示 2 天），執行此腳本即可修正。

使用：在 bot 目錄下執行（需已安裝 supabase、python-dotenv）
  python recompute_streaks.py
"""
import os
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])


def recompute_streaks():
    all_checkins = supabase.table("checkins").select("member_id, date").execute().data
    print(f"資料庫總共 {len(all_checkins)} 筆打卡:")
    for r in all_checkins:
        print(f"  member_id={str(r['member_id'])[:8]}... date={r['date']}")

    members = supabase.table("members").select("id, display_name").execute().data
    for m in members:
        mid = m["id"]
        name = m.get("display_name", mid[:8])
        rows = supabase.table("checkins").select("date").eq("member_id", mid).order("date").execute().data
        dates = sorted({r["date"] for r in rows})
        if not dates:
            supabase.table("members").update({
                "current_streak": 0,
                "longest_streak": 0,
                "last_checkin_date": None,
            }).eq("id", mid).execute()
            print(f"  {name}: 0 筆打卡 -> current=0, longest=0")
            continue
        last_date = dates[-1]
        cur = 1
        d = datetime.fromisoformat(last_date).date()
        for i in range(len(dates) - 2, -1, -1):
            prev = datetime.fromisoformat(dates[i]).date()
            if (d - prev).days == 1:
                cur += 1
                d = prev
            else:
                break
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
        print(f"  {name}: {len(dates)} 筆 {dates} -> current={cur}, longest={longest}")
    print("recompute_streaks done.")


if __name__ == "__main__":
    recompute_streaks()
