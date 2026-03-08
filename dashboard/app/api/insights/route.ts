import { NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";

const GEMINI_API_KEY = process.env.GEMINI_API_KEY;

export async function GET() {
  if (!GEMINI_API_KEY) {
    return NextResponse.json({
      items: [
        {
          type: "tip",
          title: "尚未設定 Gemini API Key",
          content:
            "請在 Dashboard 的環境變數中設定 GEMINI_API_KEY（與 Bot 可用同一把 key）。本地開發：在 dashboard/.env.local 加上 GEMINI_API_KEY=你的key；Vercel：在 Project Settings > Environment Variables 新增。設定後重新部署或重啟 npm run dev，再重新整理此頁。",
        },
      ],
    });
  }

  const { GoogleGenAI } = await import("@google/genai");
  const ai = new GoogleGenAI({ apiKey: GEMINI_API_KEY });

  try {
    const [{ data: todayCheckins, error: todayErr }, { data: members, error: membersErr }, { data: dailyStats, error: dailyErr }] =
      await Promise.all([
        supabase.from("today_checkins").select("display_name, content"),
        supabase.from("member_overview").select("display_name, current_streak, this_week_checkins, total_checkins"),
        supabase.from("daily_stats").select("date, checkin_count"),
      ]);

    if (todayErr) console.error("Error fetching today_checkins:", todayErr);
    if (membersErr) console.error("Error fetching member_overview:", membersErr);
    if (dailyErr) console.error("Error fetching daily_stats:", dailyErr);

    const totalMembers = members?.length ?? 0;
    const todayCount = todayCheckins?.length ?? 0;
    const checkinRate = totalMembers ? Math.round((todayCount / totalMembers) * 100) : 0;
    const activeStreakers = (members || []).filter((m: any) => (m.current_streak || 0) >= 3).length;

    const recentTrend = (dailyStats || []).slice(-7);

    const trendSummary = recentTrend
      .map((d: any) => `${d.date}: ${d.checkin_count} 人`)
      .join("\n");

    const sampleLines = (todayCheckins || [])
      .slice(0, 25)
      .map((c: any) => `- ${c.display_name}: ${String(c.content || "").slice(0, 80)}`)
      .join("\n");

    const prompt = `
你是一個協助 Discord 求職群組管理員的「群組動能分析助手」。

請根據以下數據，產出一段給管理員看的「AI 洞察」，幫助他們快速掌握本週與今天的狀況，並給出具體建議。

【整體數據】
- 總成員數：${totalMembers} 人
- 今日已有打卡：${todayCount} 人（約 ${checkinRate}%）
- 目前連續打卡 ≥ 3 天的成員：${activeStreakers} 人

【最近 7 天每日打卡人數】
${trendSummary || "（目前沒有足夠的歷史資料）"}

【今日部分打卡內容（截斷顯示）】
${sampleLines || "（今天暫時還沒有打卡內容）"}

請用以下格式輸出一段約 120-180 字的文字：
1. 先用 1-2 句話總結目前群組的整體動能與氛圍（可提到打卡率、高連續天數成員比例等）
2. 接著給出 1-2 個具體、可執行的管理建議（例如：要提醒哪些成員、是否適合辦活動、是否要調整提醒時間）

語氣請：
- 使用繁體中文
- 像是和主揪說話的專業顧問，溫暖但不廢話
- 不要列點，直接用自然段落描述即可
`;

    const response = await ai.models.generateContent({
      model: "gemini-2.5-flash",
      contents: prompt,
    });

    const text =
      (response as any)?.text ||
      "目前無法從 Gemini 取得分析結果，但你可以先從 Dashboard 的打卡率與連續天數，粗略判斷群組目前的動能狀態。";

    return NextResponse.json({
      items: [
        {
          type: "trend",
          title: "本週群組 AI 洞察",
          content: text.trim(),
        },
      ],
    });
  } catch (error) {
    console.error("Unexpected error in /api/insights:", error);
    return NextResponse.json({
      items: [
        {
          type: "tip",
          title: "AI 洞察暫時不可用",
          content:
            "目前無法取得 Gemini 分析結果，請稍後再試。你仍可透過上方的「今日打卡」、「未打卡」與每日圖表，快速了解群組現在的狀況。",
        },
      ],
    });
  }
}

