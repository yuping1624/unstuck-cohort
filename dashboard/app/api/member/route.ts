import { NextRequest, NextResponse } from "next/server";
import { supabase } from "@/lib/supabase";

export async function GET(req: NextRequest) {
    const { searchParams } = new URL(req.url);
    const discordId = searchParams.get("discord_id");

    if (!discordId) {
        return NextResponse.json({ error: "缺少 discord_id 參數" }, { status: 400 });
    }

    try {
        const { data: me, error: meErr } = await supabase
            .from("member_overview")
            .select("*")
            .eq("discord_id", discordId)
            .single();

        if (meErr || !me) {
            console.error("Error fetching member_overview:", meErr);
            return NextResponse.json(
                { error: "找不到對應成員，請確認 Discord ID 是否正確。" },
                { status: 404 },
            );
        }

        const { data: checkinsRaw, error: checkinsErr } = await supabase
            .from("checkins")
            .select("id, content, date, created_at")
            .eq("member_id", me.id)
            .order("date", { ascending: false })
            .order("created_at", { ascending: false })
            .limit(50);

        if (checkinsErr) {
            console.error("Error fetching member checkins:", checkinsErr);
        }

        const checkinIds = (checkinsRaw || []).map((c: any) => c.id);
        const repliesByCheckinId: Record<string, string | null> = {};

        if (checkinIds.length > 0) {
            const { data: repliesRaw, error: repliesErr } = await supabase
                .from("ai_replies")
                .select("checkin_id, reply, created_at")
                .in("checkin_id", checkinIds)
                .order("created_at", { ascending: false });

            if (repliesErr) {
                console.error("Error fetching ai_replies:", repliesErr);
            } else {
                for (const r of (repliesRaw || []) as any[]) {
                    if (!repliesByCheckinId[r.checkin_id]) {
                        repliesByCheckinId[r.checkin_id] = r.reply;
                    }
                }
            }
        }

        const normalizedCheckins = (checkinsRaw || []).map((row: any) => ({
            id: row.id,
            content: row.content,
            date: row.date,
            created_at: row.created_at,
            display_name: me.display_name,
            ai_reply: repliesByCheckinId[row.id] ?? null,
        }));

        const { data: allMembers, error: membersErr } = await supabase
            .from("member_overview")
            .select("*");

        if (membersErr) {
            console.error("Error fetching members:", membersErr);
        }

        return NextResponse.json({
            me,
            checkins: normalizedCheckins,
            members: allMembers || [],
        });
    } catch (error) {
        console.error("Unexpected error in /api/member:", error);
        return NextResponse.json(
            { error: "讀取成員資料時發生錯誤，請稍後再試。" },
            { status: 500 },
        );
    }
}

