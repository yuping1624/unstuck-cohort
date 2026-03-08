import React from "react";

export function StatCard({ label, value, sub, color }: { label: string; value: number | string; sub: string; color: string }) {
    const colors: Record<string, string> = {
        blue: "text-blue-400 border-blue-500",
        green: "text-green-400 border-green-500",
        yellow: "text-yellow-400 border-yellow-500",
        purple: "text-purple-400 border-purple-500",
    };
    const fallbackColor = "text-slate-400 border-slate-500";
    const [textColor, borderColor] = (colors[color] || fallbackColor).split(" ");

    return (
        <div className={`bg-[#12151c] border border-slate-800 rounded-xl p-4 border-t-2 ${borderColor}`}>
            <div className="text-xs text-slate-500 uppercase tracking-wider mb-2">{label}</div>
            <div className={`text-3xl font-bold font-mono ${textColor}`}>{value}</div>
            <div className="text-xs text-slate-500 mt-1">{sub}</div>
        </div>
    );
}
