"use client";

import { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Avatar, WeekDots, CheckinModal, ViewToggle } from "@/components/TemplateComponents";

type MemberOverview = {
    id: string;
    display_name: string;
    current_streak: number;
    longest_streak: number;
    total_checkins: number;
    this_week_checkins: number;
    timezone?: string;
};

type MemberCheckin = {
    id: string;
    content: string;
    date: string;
    created_at: string;
    display_name: string;
    ai_reply?: string | null;
};

type MemberApiResponse = {
    me: MemberOverview;
    checkins: MemberCheckin[];
    members: MemberOverview[];
};

export default function HomePage() {
    return (
        <Suspense fallback={
            <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh", background: "var(--app-bg)", color: "var(--text)" }}>
                Loading...
            </div>
        }>
            <HomePageContent />
        </Suspense>
    );
}

function HomePageContent() {
    const searchParams = useSearchParams();
    const discordId = searchParams.get("discord_id");
    const [data, setData] = useState<MemberApiResponse | null>(null);
    const [selectedCheckin, setSelectedCheckin] = useState<MemberCheckin | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const id = (discordId || "").trim();

        if (!id) {
            setLoading(false);
            setData(null);
            setError(null);
            return;
        }

        setLoading(true);
        setError(null);

        fetch(`/api/member?discord_id=${encodeURIComponent(id)}`)
            .then(async (r) => {
                if (!r.ok) {
                    const body = await r.json().catch(() => ({}));
                    throw new Error(body.error || "載入失敗，請稍後再試。");
                }
                return r.json();
            })
            .then((res: MemberApiResponse) => {
                setData(res);
            })
            .catch((e: any) => {
                console.error(e);
                setError(e.message || "載入失敗，請稍後再試。");
            })
            .finally(() => setLoading(false));
    }, [discordId]);

    if (loading) {
        return (
            <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh", background: "var(--app-bg)", color: "var(--text)" }}>
                Loading...
            </div>
        );
    }

    if (error || !data) {
        const isNoId = !(discordId || "").trim();
        return (
            <div style={{ minHeight: "100vh", background: "var(--app-bg)", color: "var(--text)", display: "flex", alignItems: "center", justifyContent: "center", padding: 24, textAlign: "center" }}>
                <ViewToggle currentView="member" showAdminLink={false} />
                <div style={{ maxWidth: 420 }}>
                    {isNoId ? (
                        <>
                            <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 8 }}>成員專屬頁面</div>
                            <div style={{ fontSize: 13, color: "var(--muted)", lineHeight: 1.7 }}>
                                請在 Discord 對 Bot 輸入 <strong style={{ color: "var(--text)" }}>!me</strong>，Bot 會私訊你專屬連結，點擊後即可看到個人打卡數據。
                            </div>
                        </>
                    ) : (
                        <>
                            <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 8 }}>無法載入成員資料</div>
                            <div style={{ fontSize: 13, color: "var(--muted)", marginBottom: 12 }}>
                                {error || "請確認網址是否正確。"}
                            </div>
                        </>
                    )}
                </div>
            </div>
        );
    }

    const { me, checkins, members } = data;
    const memberTz = me.timezone || "Asia/Taipei";
    const TODAY = (() => {
        try {
            return new Date().toLocaleDateString("en-CA", { timeZone: memberTz });
        } catch {
            return new Date().toISOString().slice(0, 10);
        }
    })();
    const startStr = "2026-03-09";
    const daysFromStart = Math.round((new Date(TODAY).getTime() - new Date(startStr).getTime()) / 86400000);
    const week = daysFromStart < 0 ? 0 : Math.min(12, Math.floor(daysFromStart / 7) + 1);
    const weekPct = (week / 12) * 100;
    const streakPct = Math.min((me.current_streak / 21) * 100, 100);

    function getWeekForMember(m: { timezone?: string }) {
        const tz = m.timezone || "Asia/Taipei";
        try {
            const todayStr = new Date().toLocaleDateString("en-CA", { timeZone: tz });
            const d = Math.round((new Date(todayStr).getTime() - new Date(startStr).getTime()) / 86400000);
            return d < 0 ? 0 : Math.min(12, Math.floor(d / 7) + 1);
        } catch {
            return week;
        }
    }
    const sameWeekMembers = members.filter((m: any) => getWeekForMember(m) === week);
    const rankedMembers = sameWeekMembers.filter((m: any) => (m.total_checkins || 0) > 0);
    const sortedMembers = [...rankedMembers].sort((a: any, b: any) => b.current_streak - a.current_streak);
    const rankByMemberId: Record<string, number> = {};
    sortedMembers.forEach((m: any, i: number) => {
        const sameAsPrev = i > 0 && m.current_streak === sortedMembers[i - 1].current_streak;
        rankByMemberId[m.id] = sameAsPrev ? rankByMemberId[sortedMembers[i - 1].id]! : i + 1;
    });
    const myRank = rankByMemberId[me.id];
    const myRankLabel = myRank != null ? `#${myRank}` : "-";

    return (
        <div style={{ minHeight: "100vh", background: "var(--app-bg)", color: "var(--text)" }}>
            <ViewToggle currentView="member" showAdminLink={false} />

            <div style={{ maxWidth: 680, margin: "0 auto", padding: "28px 20px 60px" }}>
                <div className="fade-up" style={{ marginBottom: 28 }}>
                    <div style={{ display: "flex", alignItems: "flex-start", gap: 16, marginBottom: 20 }}>
                        <Avatar name={me.display_name} size={52} />
                        <div>
                            <div style={{ fontSize: 22, fontWeight: 700, letterSpacing: "-0.02em" }}>
                                嗨，{me.display_name} 👋
                            </div>
                            <div style={{ fontSize: 13, color: "var(--muted2)", marginTop: 3 }}>
                                {week === 0 ? "第 0 週（3/9 起第 1 週）" : <>第 <span style={{ color: "var(--text)", fontWeight: 600 }}>{week}</span> 週</>} · 你已經連續打卡 <span style={{ color: "var(--warning)", fontWeight: 700 }}>{me.current_streak} 天</span>
                            </div>
                        </div>
                    </div>

                    <div style={{
                        background: "linear-gradient(135deg, var(--card-bg), var(--card-bg-alt))",
                        border: "1px solid var(--border-light)",
                        borderRadius: 20, padding: "24px 24px 20px",
                        position: "relative", overflow: "hidden",
                    }}>
                        <div style={{ position: "absolute", top: -40, right: -40, width: 160, height: 160, background: "radial-gradient(circle, rgba(245,158,11,0.12), transparent 70%)", pointerEvents: "none" }} />

                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18 }}>
                            <div>
                                <div style={{ fontSize: 11, color: "var(--muted2)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 6 }}>連續打卡</div>
                                <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                                    <span style={{ fontSize: 48, fontWeight: 700, fontFamily: "'DM Mono', monospace", color: "var(--warning)", lineHeight: 1 }}>{me.current_streak}</span>
                                    <span style={{ fontSize: 16, color: "var(--muted2)" }}>天</span>
                                </div>
                            </div>
                            <div style={{ textAlign: "right" }}>
                                <div style={{ fontSize: 11, color: "var(--muted2)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 4 }}>最長紀錄</div>
                                <div style={{ fontSize: 22, fontWeight: 700, fontFamily: "'DM Mono', monospace", color: "var(--muted)" }}>{me.longest_streak}</div>
                                <div style={{ fontSize: 11, color: "var(--muted2)" }}>總計 {me.total_checkins} 天</div>
                            </div>
                        </div>

                        <StreakDots checkins={checkins} total={21} TODAY={TODAY} />

                        <div style={{ marginTop: 16, display: "flex", gap: 12 }}>
                            <div style={{ flex: 1 }}>
                                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
                                    <span style={{ fontSize: 11, color: "var(--muted2)" }}>連續打卡目標</span>
                                    <span style={{ fontSize: 11, color: "var(--warning)", fontFamily: "'DM Mono', monospace" }}>{me.current_streak}/21</span>
                                </div>
                                <div style={{ height: 5, background: "var(--border)", borderRadius: 3 }}>
                                    <div style={{ height: 5, background: "linear-gradient(90deg, var(--warning), var(--danger))", borderRadius: 3, width: `${streakPct}%`, transition: "width 1s ease" }} />
                                </div>
                            </div>
                            <div style={{ flex: 1 }}>
                                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
                                    <span style={{ fontSize: 11, color: "var(--muted2)" }}>12 週計畫進度</span>
                                    <span style={{ fontSize: 11, color: "var(--accent)", fontFamily: "'DM Mono', monospace" }}>{week}/12 週</span>
                                </div>
                                <div style={{ height: 5, background: "var(--border)", borderRadius: 3 }}>
                                    <div style={{ height: 5, background: "linear-gradient(90deg, var(--accent), #7c3aed)", borderRadius: 3, width: `${weekPct}%`, transition: "width 1s ease" }} />
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="fade-up-1" style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginBottom: 24 }}>
                    {[
                        { label: "本週打卡", value: me.this_week_checkins, unit: "天", color: "var(--success)" },
                        { label: "累計打卡", value: me.total_checkins, unit: "天", color: "var(--accent)" },
                        { label: "群組排名", value: myRankLabel, unit: "", color: "var(--warning)" },
                    ].map(({ label, value, unit, color }) => (
                        <div key={label} style={{ background: "var(--card-bg)", border: "1px solid var(--border)", borderRadius: 14, padding: "14px 16px", textAlign: "center" }}>
                            <div style={{ fontSize: 10, color: "var(--muted2)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>{label}</div>
                            <div style={{ fontSize: 24, fontWeight: 700, fontFamily: "'DM Mono', monospace", color }}>{value}<span style={{ fontSize: 13, color: "var(--muted2)" }}>{unit}</span></div>
                        </div>
                    ))}
                </div>

                <div className="fade-up-2">
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
                        <h2 style={{ fontSize: 14, fontWeight: 600 }}>📝 我的打卡紀錄</h2>
                        <span style={{ fontSize: 11, color: "var(--muted2)" }}>點擊卡片可展開完整 AI 回覆</span>
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                        {checkins.map((c, i) => (
                            <MemberCheckinCard key={c.id || i} checkin={c} isToday={c.date === TODAY || c.created_at?.includes(TODAY)} delay={i * 0.05} onClick={() => setSelectedCheckin(c)} />
                        ))}
                    </div>
                </div>

                <div className="fade-up-3" style={{ marginTop: 24 }}>
                    <h2 style={{ fontSize: 14, fontWeight: 600, marginBottom: 14 }}>🔥 本週連續打卡排行</h2>
                    <div style={{ background: "var(--card-bg)", border: "1px solid var(--border)", borderRadius: 16, overflow: "hidden" }}>
                        {sortedMembers.slice(0, 6).map((m, i) => {
                            const rank = rankByMemberId[m.id] ?? 0;
                            const rankDisplay = rank === 1 ? "🥇" : rank === 2 ? "🥈" : rank === 3 ? "🥉" : rank;
                            return (
                            <div key={m.id} className="hoverable" style={{
                                display: "flex", alignItems: "center", gap: 12, padding: "12px 16px",
                                borderBottom: i < 5 ? "1px solid var(--card-bg-alt)" : "none",
                                background: m.id === me.id ? "var(--accent-soft)" : "transparent",
                            }}>
                                <span style={{ fontSize: 13, color: "var(--muted3)", width: 18, textAlign: "center", fontFamily: "'DM Mono', monospace" }}>
                                    {rankDisplay}
                                </span>
                                <Avatar name={m.display_name} size={28} />
                                <div style={{ flex: 1, fontSize: 13, fontWeight: m.id === me.id ? 600 : 400 }}>
                                    {m.display_name}
                                    {m.id === me.id && <span style={{ fontSize: 10, color: "var(--accent)", marginLeft: 6 }}>（你）</span>}
                                </div>
                                <WeekDots member={m} today={TODAY} />
                                <span style={{ fontSize: 12, fontFamily: "'DM Mono', monospace", color: "var(--warning)", width: 40, textAlign: "right" }}>{m.current_streak}🔥</span>
                            </div>
                            );
                        })}
                    </div>
                </div>
            </div>

            {selectedCheckin && (
                <CheckinModal checkin={selectedCheckin} onClose={() => setSelectedCheckin(null)} />
            )}
        </div>
    );
}

function StreakDots({ checkins, total, TODAY }: { checkins: MemberCheckin[]; total: number; TODAY: string }) {
    const checkinDates = new Set(checkins.map(c => c.date || c.created_at?.slice(0, 10)));
    const today = new Date(TODAY);
    const dots = Array.from({ length: total }, (_, i) => {
        const d = new Date(today);
        d.setDate(today.getDate() - (total - 1 - i));
        const dateStr = d.toISOString().slice(0, 10);
        return { dateStr, checked: checkinDates.has(dateStr), isToday: i === total - 1 };
    });
    return (
        <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            {dots.map(({ dateStr, checked, isToday }) => (
                <div key={dateStr} title={dateStr} style={{
                    width: 14, height: 14, borderRadius: 3,
                    background: isToday ? (checked ? "var(--accent)" : "var(--border-light)") : checked ? "var(--success)" : "var(--border)",
                    boxShadow: isToday && checked ? "0 0 8px var(--accent-border)" : "none",
                    border: isToday ? "1px solid var(--accent-border)" : "none",
                    transition: "background 0.2s",
                }} />
            ))}
        </div>
    );
}

function MemberCheckinCard({ checkin, isToday, delay, onClick }: { checkin: MemberCheckin; isToday: boolean; delay: number; onClick: () => void }) {
    const dateStr = checkin.date || checkin.created_at?.slice(0, 10);
    const date = new Date(dateStr);
    const dayNames = ["日", "一", "二", "三", "四", "五", "六"];
    return (
        <div onClick={onClick} style={{
            display: "flex", gap: 14, padding: "14px 16px",
            background: isToday ? "var(--accent-soft)" : "var(--card-bg)",
            border: `1px solid ${isToday ? "var(--accent-border)" : "var(--border)"}`,
            borderRadius: 14, cursor: "pointer",
            animation: `fadeUp 0.35s ${delay}s ease both`,
            transition: "border-color 0.2s, transform 0.15s",
        }}
            onMouseEnter={e => e.currentTarget.style.transform = "translateY(-1px)"}
            onMouseLeave={e => e.currentTarget.style.transform = ""}
        >
            <div style={{ width: 38, textAlign: "center", flexShrink: 0 }}>
                <div style={{ fontSize: 18, fontWeight: 700, fontFamily: "'DM Mono', monospace", color: isToday ? "var(--accent)" : "var(--muted)", lineHeight: 1 }}>
                    {String(date.getDate()).padStart(2, "0")}
                </div>
                <div style={{ fontSize: 10, color: "var(--muted3)", marginTop: 2 }}>週{dayNames[date.getDay()]}</div>
                {isToday && <div style={{ fontSize: 9, color: "var(--accent)", marginTop: 3, fontWeight: 600 }}>今天</div>}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
                <p style={{ fontSize: 13, lineHeight: 1.6, color: "var(--text-soft)" }}>{checkin.content}</p>
                {checkin.ai_reply && (
                    <div style={{ marginTop: 8, padding: "8px 10px", background: "var(--accent-soft)", borderLeft: "2px solid var(--accent-border)", borderRadius: "0 6px 6px 0" }}>
                        <div style={{ fontSize: 10, color: "var(--accent)", marginBottom: 3, fontWeight: 600 }}>✨ AI 回覆</div>
                        <p style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5 }}>{checkin.ai_reply.slice(0, 80)}…</p>
                    </div>
                )}
            </div>
        </div>
    );
}
