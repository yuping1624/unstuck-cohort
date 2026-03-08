import React from "react";

export function WeekDots({ member, todayDate }: { member: any, todayDate: string }) {
    const today = new Date(todayDate);
    return (
        <div style={{ display: "flex", gap: 3 }}>
            {Array.from({ length: 7 }, (_, i) => {
                const d = new Date(today);
                d.setDate(today.getDate() - (6 - i));
                const dateStr = d.toISOString().slice(0, 10);
                const isToday = i === 6;
                const checked = dateStr <= (member.last_checkin_date || "") && Math.random() > (1 - member.this_week_checkins / 7);
                return (
                    <div key={i} style={{
                        width: 11, height: 11, borderRadius: 3,
                        background: isToday
                            ? (member.last_checkin_date === todayDate ? "#4f8ef7" : "#252a38")
                            : checked ? "#22c55e" : "#1e2433",
                        border: isToday ? "1px solid rgba(79,142,247,0.4)" : "none",
                    }} />
                );
            })}
        </div>
    );
}
