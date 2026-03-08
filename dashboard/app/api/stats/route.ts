import { NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";

// 強制每次請求都重新打 DB，避免 Dashboard 數字與 AI 洞察不一致（例如洞察已顯示 1 人打卡、上方卡片仍顯示 0）
export const dynamic = "force-dynamic";

export async function GET() {
    try {
        const { data: todayCheckins, error: todayErr } = await supabase
            .from("today_checkins")
            .select("*");

        if (todayErr) {
            console.error("Error fetching today_checkins:", todayErr);
        }

        const { data: members, error: membersErr } = await supabase
            .from("member_overview")
            .select("*");

        if (membersErr) {
            console.error("Error fetching members:", membersErr);
        }

        const { data: dailyStats } = await supabase
            .from("daily_stats")
            .select("*");

        // 近 28 天每人打卡日期（給「成員出勤預覽表」用）
        const today = new Date().toISOString().slice(0, 10);
        const start = new Date(today);
        start.setDate(start.getDate() - 28);
        const startStr = start.toISOString().slice(0, 10);

        const { data: recentCheckins } = await supabase
            .from("checkins")
            .select("member_id, date")
            .gte("date", startStr)
            .lte("date", today);

        const attendance: Record<string, string[]> = {};
        for (const row of recentCheckins || []) {
            const id = row.member_id;
            if (!attendance[id]) attendance[id] = [];
            if (!attendance[id].includes(row.date)) attendance[id].push(row.date);
        }

        const data = {
            today: todayCheckins || [],
            daily: dailyStats || [],
            members: members || [],
            attendance,
        };

        return NextResponse.json(data, {
            headers: {
                "Cache-Control": "no-store, max-age=0",
            },
        });
    } catch (error) {
        return NextResponse.json({ error: "Failed to fetch stats" }, { status: 500 });
    }
}
