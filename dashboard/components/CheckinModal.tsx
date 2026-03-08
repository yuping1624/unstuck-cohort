import React from "react";
import { Avatar } from "./ui/Avatar";

export function CheckinModal({ checkin, onClose }: { checkin: any; onClose: () => void }) {
    if (!checkin) return null;

    return (
        <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={(e) => e.target === e.currentTarget && onClose()}>
            <div className="bg-[#12151c] border border-slate-700 rounded-2xl w-full max-w-md p-6">
                <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3">
                        <Avatar name={checkin.display_name} size={36} />
                        <div>
                            <h3 className="font-semibold">{checkin.display_name}</h3>
                            <div className="text-xs text-slate-500">
                                {new Date(checkin.created_at || checkin.date).toLocaleString("zh-TW", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                                {checkin.current_streak > 1 && <span className="text-yellow-400 ml-2">🔥{checkin.current_streak} 天</span>}
                            </div>
                        </div>
                    </div>
                    <button onClick={onClose} className="text-slate-500 hover:text-slate-300 text-sm p-1 rounded">✕</button>
                </div>

                <div className="space-y-4">
                    <div className="bg-[#0d0f14] rounded-lg p-4">
                        <div className="text-xs text-slate-500 uppercase tracking-wider mb-2">打卡內容</div>
                        <div className="text-sm leading-relaxed text-slate-300 whitespace-pre-wrap">{checkin.content}</div>
                    </div>

                    {checkin.ai_reply && (
                        <div className="bg-gradient-to-br from-blue-500/10 to-purple-500/10 border border-blue-500/20 rounded-lg p-4">
                            <div className="text-xs text-blue-400 font-bold uppercase tracking-wider mb-2">✨ AI 回覆</div>
                            <div className="text-sm leading-relaxed text-slate-400 whitespace-pre-wrap">{checkin.ai_reply}</div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
