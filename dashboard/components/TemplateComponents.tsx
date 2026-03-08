"use client";

import React from "react";
import { useTheme } from "@/contexts/ThemeContext";

const avatarColors = [
    ["#4f8ef7", "#7c3aed"], ["#22c55e", "#16a34a"], ["#f59e0b", "#d97706"],
    ["#ec4899", "#be185d"], ["#06b6d4", "#0891b2"], ["#8b5cf6", "#6d28d9"],
];

const getAvatarColor = (name: string) => avatarColors[name.charCodeAt(0) % avatarColors.length] || avatarColors[0];

export function Avatar({ name, size = 36 }: { name: string, size?: number }) {
    const colors = getAvatarColor(name);
    return (
        <div style={{
            width: size, height: size, borderRadius: "50%",
            background: `linear-gradient(135deg, ${colors[0]}, ${colors[1]})`,
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: size * 0.38, fontWeight: 700, flexShrink: 0, color: "white",
        }}>
            {name?.[0] || "?"}
        </div>
    );
}

export function WeekDots({ member, today = new Date().toISOString().slice(0, 10) }: { member: any, today?: string }) {
    const todayDate = new Date(today);
    return (
        <div style={{ display: "flex", gap: 3 }}>
            {Array.from({ length: 7 }, (_, i) => {
                const d = new Date(todayDate);
                d.setDate(todayDate.getDate() - (6 - i));
                const dateStr = d.toISOString().slice(0, 10);
                const isToday = i === 6;
                const checked = dateStr <= (member.last_checkin_date || "") && (member.this_week_checkins > 6 - i);
                return (
                    <div key={i} style={{
                        width: 11, height: 11, borderRadius: 3,
                        background: isToday
                            ? (member.last_checkin_date === today ? "var(--accent)" : "var(--border-light)")
                            : checked ? "var(--success)" : "var(--border)",
                        border: isToday ? "1px solid var(--accent-border)" : "none",
                    }} />
                );
            })}
        </div>
    );
}

export function CheckinModal({ checkin, onClose }: { checkin: any, onClose: () => void }) {
    return (
        <div onClick={e => e.target === e.currentTarget && onClose()} style={{
            position: "fixed", inset: 0, background: "var(--overlay)", zIndex: 200,
            display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
        }}>
            <div style={{
                background: "var(--card-bg)", border: "1px solid var(--border-light)", borderRadius: 20,
                width: "100%", maxWidth: 460, padding: 24,
                animation: "fadeUp 0.25s ease both",
            }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <Avatar name={checkin.display_name} size={36} />
                        <div>
                            <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text)" }}>{checkin.display_name}</div>
                            <div style={{ fontSize: 11, color: "var(--muted3)" }}>
                                {new Date(checkin.created_at || checkin.date).toLocaleString("zh-TW", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                                {checkin.current_streak > 1 && <span style={{ color: "var(--warning)", marginLeft: 6 }}>🔥{checkin.current_streak} 天</span>}
                            </div>
                        </div>
                    </div>
                    <button onClick={onClose} style={{ background: "none", border: "1px solid var(--border-light)", color: "var(--muted2)", borderRadius: 8, padding: "4px 10px", cursor: "pointer", fontSize: 12, fontFamily: "inherit" }}>✕</button>
                </div>
                <div style={{ background: "var(--app-bg)", borderRadius: 12, padding: 14, marginBottom: 14 }}>
                    <div style={{ fontSize: 11, color: "var(--muted3)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>打卡內容</div>
                    <p style={{ fontSize: 14, lineHeight: 1.7, color: "var(--text-soft)" }}>{checkin.content}</p>
                </div>
                {checkin.ai_reply && (
                    <div style={{ background: "var(--accent-soft)", border: "1px solid var(--accent-border)", borderRadius: 12, padding: 14 }}>
                        <div style={{ fontSize: 11, color: "var(--accent)", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: 700, marginBottom: 8 }}>✨ AI 回覆</div>
                        <p style={{ fontSize: 13, lineHeight: 1.7, color: "var(--muted)" }}>{checkin.ai_reply}</p>
                    </div>
                )}
            </div>
        </div>
    );
}

export function ViewToggle({ currentView, showAdminLink = true }: { currentView: "member" | "admin"; showAdminLink?: boolean }) {
    const { theme, toggleTheme } = useTheme();
    return (
        <div style={{ position: "fixed", top: 16, right: 20, zIndex: 100, display: "flex", alignItems: "center", gap: 8 }}>
            <button
                type="button"
                onClick={toggleTheme}
                title={theme === "dark" ? "切換淺色模式" : "切換深色模式"}
                className="btn-switch"
                style={{
                    width: 36, height: 36, borderRadius: 10, border: "1px solid var(--border-light)",
                    background: "var(--card-bg)", color: "var(--muted)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18, cursor: "pointer",
                }}
            >
                {theme === "dark" ? "☀️" : "🌙"}
            </button>
        </div>
    );
}
