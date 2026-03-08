"use client";

import { useCallback, useEffect, useState } from "react";
import { Avatar, WeekDots, CheckinModal, ViewToggle } from "@/components/TemplateComponents";

export default function AdminDashboard() {
  const [authorized, setAuthorized] = useState(false);
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [loggingIn, setLoggingIn] = useState(false);

  const [data, setData] = useState<{ today: any[], daily: any[], members: any[], attendance?: Record<string, string[]> } | null>(null);
  const [selectedCheckin, setSelectedCheckin] = useState<any>(null);
  const [tab, setTab] = useState("today");
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(() => {
    fetch("/api/stats")
      .then((r) => r.json())
      .then((res) => {
        setData(res);
        setLastUpdated(new Date());
      })
      .catch((err) => console.error(err))
      .finally(() => setRefreshing(false));
  }, []);

  // 檢查是否已登入管理員
  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        setCheckingAuth(true);
        const res = await fetch("/api/admin/session");
        if (cancelled) return;
        if (res.ok) {
          setAuthorized(true);
          setAuthError(null);
        } else {
          setAuthorized(false);
        }
      } catch (e: any) {
        if (!cancelled) {
          console.error(e);
          setAuthorized(false);
          setAuthError(e.message || "驗證失敗，請稍後再試。");
        }
      } finally {
        if (!cancelled) setCheckingAuth(false);
      }
    };
    check();
    return () => {
      cancelled = true;
    };
  }, []);

  // 已通過驗證才載入 Dashboard 資料
  useEffect(() => {
    if (!authorized) return;
    load();
    const interval = setInterval(load, 30_000);
    return () => clearInterval(interval);
  }, [authorized, load]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password.trim()) return;
    try {
      setLoggingIn(true);
      setAuthError(null);
      const res = await fetch("/api/admin/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || "密碼錯誤");
      }
      setAuthorized(true);
      setPassword("");
    } catch (e: any) {
      console.error(e);
      setAuthError(e.message || "登入失敗，請稍後再試。");
      setPassword("");
    } finally {
      setLoggingIn(false);
    }
  };

  if (checkingAuth) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh", background: "var(--app-bg)", color: "var(--text)", fontSize: 13 }}>
        正在驗證管理員身份…
      </div>
    );
  }

  if (!authorized) {
    return (
      <div style={{ minHeight: "100vh", background: "var(--app-bg)", color: "var(--text)", display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
        <ViewToggle currentView="admin" />
        <div style={{ maxWidth: 360, width: "100%", background: "var(--card-bg)", border: "1px solid var(--border)", borderRadius: 16, padding: 20, boxShadow: "0 18px 45px rgba(0,0,0,0.45)" }}>
          <div style={{ fontSize: 18, fontWeight: 700, marginBottom: 8 }}>管理員登入</div>
          <div style={{ fontSize: 13, color: "var(--muted)", marginBottom: 14 }}>
            請輸入你設定在 `ADMIN_PASSWORD` 的密碼，僅管理員應該知道此密碼。
          </div>
          <form onSubmit={handleLogin} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="管理員密碼"
              style={{
                background: "var(--input-bg)",
                borderRadius: 10,
                border: "1px solid var(--border-light)",
                padding: "8px 10px",
                fontSize: 13,
                color: "var(--text)",
                outline: "none",
              }}
            />
            {authError && (
              <div style={{ fontSize: 12, color: "var(--danger)" }}>{authError}</div>
            )}
            <button
              type="submit"
              disabled={loggingIn}
              style={{
                marginTop: 4,
                padding: "8px 10px",
                borderRadius: 10,
                border: "none",
                fontSize: 13,
                fontWeight: 600,
                cursor: loggingIn ? "wait" : "pointer",
                background: "var(--accent)",
                color: "white",
              }}
            >
              {loggingIn ? "登入中…" : "登入後台"}
            </button>
          </form>
        </div>
      </div>
    );
  }

  if (!data) return <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh", background: "var(--app-bg)", color: "var(--text)" }}>Loading...</div>;

  const start = new Date("2026-03-09");
  const elapsed = Date.now() - start.getTime();
  const week = elapsed < 0 ? 0 : Math.min(Math.floor(elapsed / (7 * 86400000)) + 1, 12);
  const todayCount = data.today.length;
  const totalMembers = data.members.length;
  const TODAY = new Date().toISOString().slice(0, 10);

  const todayUserIds = data.today.map(c => c.member_id || c.discord_id);
  const notCheckedInMembers = data.members.filter(m => !todayUserIds.includes(m.id) && !todayUserIds.includes(m.discord_id));
  const notCheckedInCount = notCheckedInMembers.length;

  const topStreak = data.members.length > 0 ? Math.max(...data.members.map(m => m.current_streak)) : 0;

  const activeThisWeek = data.members.filter((m: any) => (m.this_week_checkins || 0) > 0).length;
  const notCheckedInThisWeek = data.members.filter((m: any) => (m.this_week_checkins || 0) === 0);

  const avgThisWeek = data.members.length > 0 ? (data.members.reduce((acc, m) => acc + m.this_week_checkins, 0) / 7).toFixed(1) : "0";

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "var(--app-bg)", color: "var(--text)" }}>
      <ViewToggle currentView="admin" />

      <div style={{ width: 200, background: "var(--sidebar-bg)", borderRight: "1px solid var(--border)", padding: "20px 0", position: "fixed", height: "100vh", display: "flex", flexDirection: "column" }}>
        <div style={{ padding: "0 16px 20px", borderBottom: "1px solid var(--border)", marginBottom: 12 }}>
          <div style={{ width: 32, height: 32, background: "linear-gradient(135deg, var(--accent), #7c3aed)", borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, marginBottom: 8 }}>🎯</div>
          <div style={{ fontSize: 13, fontWeight: 700 }}>求職 12 週</div>
          <div style={{ fontSize: 10, color: "var(--muted3)", fontFamily: "'DM Mono', monospace", marginTop: 2 }}>ADMIN PANEL</div>
        </div>
        {[
          ["today", "📋", "今日打卡"],
          ["members", "👥", "成員管理"],
          ["activity", "📊", "活躍統計"],
          ["insights", "✨", "AI 洞察"],
        ].map(([id, icon, label]) => (
          <button key={id} onClick={() => setTab(id)} style={{
            display: "flex", alignItems: "center", gap: 8,
            padding: "8px 16px", margin: "1px 8px", borderRadius: 8,
            border: "none", cursor: "pointer", fontSize: 12, fontFamily: "inherit",
            background: tab === id ? "var(--accent-soft)" : "transparent",
            color: tab === id ? "var(--accent)" : "var(--muted2)",
            fontWeight: tab === id ? 600 : 400,
            transition: "all 0.15s",
          }}>
            <span style={{ fontSize: 14 }}>{icon}</span> {label}
            {id === "today" && notCheckedInCount > 0 && (
              <span style={{ marginLeft: "auto", background: "var(--danger)", color: "white", fontSize: 9, padding: "1px 5px", borderRadius: 10, fontWeight: 700 }}>{notCheckedInCount}</span>
            )}
          </button>
        ))}
        <div style={{ margin: "auto 12px 0", background: "var(--accent-soft)", border: "1px solid var(--accent-border)", borderRadius: 12, padding: 12 }}>
          <div style={{ fontSize: 30, fontWeight: 700, fontFamily: "'DM Mono', monospace", color: "var(--accent)", lineHeight: 1 }}>W{week}</div>
          <div style={{ fontSize: 10, color: "var(--muted3)", marginTop: 4 }}>{week === 0 ? "第 0 週（3/9 起第 1 週）" : `第 ${week} / 12 週`}</div>
          <div style={{ height: 3, background: "var(--border)", borderRadius: 2, marginTop: 8 }}>
            <div style={{ height: 3, background: "linear-gradient(90deg, var(--accent), #7c3aed)", borderRadius: 2, width: `${week === 0 ? 0 : (week / 12) * 100}%`, transition: "width 0.3s" }} />
          </div>
        </div>
      </div>

      <div style={{ marginLeft: 200, flex: 1, padding: "56px 28px 24px" }}>
        {lastUpdated && (
          <div style={{ fontSize: 11, color: "var(--muted2)", textAlign: "right", marginBottom: 8, display: "flex", alignItems: "center", justifyContent: "flex-end", gap: 10 }}>
            <span>最後更新：{lastUpdated.toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit" })}</span>
            <button
              type="button"
              onClick={() => { setRefreshing(true); load(); }}
              disabled={refreshing}
              style={{
                fontSize: 11, padding: "4px 10px", border: "1px solid var(--border)", borderRadius: 6,
                background: "var(--card-bg)", color: "var(--muted2)", cursor: refreshing ? "wait" : "pointer", fontFamily: "inherit",
              }}
            >
              {refreshing ? "更新中…" : "重新整理"}
            </button>
          </div>
        )}
        <div className="fade-up" style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12, marginBottom: 20 }}>
          {[
            { label: "今日打卡", val: todayCount, sub: `/ ${totalMembers} 人`, color: "var(--accent)", border: "var(--accent)" },
            { label: "今日未打卡", val: notCheckedInCount, sub: "人，需關注", color: "var(--danger)", border: "var(--danger)" },
            { label: "本週活躍", val: `${activeThisWeek} / ${totalMembers}`, sub: "人已打卡", color: "var(--success)", border: "var(--success)" },
            { label: "最長連續", val: topStreak, sub: "天 🔥", color: "var(--warning)", border: "var(--warning)" },
            { label: "本週平均", val: avgThisWeek, sub: "人/天", color: "var(--success)", border: "var(--success)" },
          ].map(({ label, val, sub, color, border }) => (
            <div key={label} style={{ background: "var(--card-bg)", border: "1px solid var(--border)", borderTop: `2px solid ${border}`, borderRadius: 12, padding: "14px 16px" }}>
              <div style={{ fontSize: 10, color: "var(--muted2)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 8 }}>{label}</div>
              <div style={{ fontSize: 24, fontWeight: 700, fontFamily: "'DM Mono', monospace", color, lineHeight: 1 }}>{val}</div>
              <div style={{ fontSize: 11, color: "var(--muted3)", marginTop: 4 }}>{sub}</div>
            </div>
          ))}
        </div>

        {tab === "today" && <AdminTodayTab data={data} TODAY={TODAY} notCheckedInMembers={notCheckedInMembers} notCheckedInThisWeek={notCheckedInThisWeek} onSelectCheckin={setSelectedCheckin} />}
        {tab === "members" && <AdminMembersTab data={data} TODAY={TODAY} />}
        {tab === "activity" && <AdminActivityTab data={data} TODAY={TODAY} />}
        {tab === "insights" && <AdminInsightsTab week={week} />}
      </div>

      {selectedCheckin && (
        <CheckinModal checkin={selectedCheckin} onClose={() => setSelectedCheckin(null)} />
      )}
    </div>
  );
}

function AdminTodayTab({ data, TODAY, notCheckedInMembers, notCheckedInThisWeek, onSelectCheckin }: { data: any, TODAY: string, notCheckedInMembers: any[], notCheckedInThisWeek: any[], onSelectCheckin: (c: any) => void }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 320px", gap: 16 }}>
      <div>
        <div className="fade-up" style={{ background: "var(--card-bg)", border: "1px solid var(--border)", borderRadius: 16, overflow: "hidden" }}>
          <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>今日打卡紀錄</span>
            <span style={{ fontSize: 11, color: "var(--muted2)" }}>{data.today.length} 則</span>
          </div>
          <div style={{ maxHeight: 520, overflowY: "auto" }}>
            {data.today.map((c: any, i: number) => (
              <div key={c.id} className="hoverable" onClick={() => onSelectCheckin(c)} style={{
                display: "flex", gap: 12, padding: "12px 18px",
                borderBottom: i < data.today.length - 1 ? "1px solid var(--card-bg-alt)" : "none",
                cursor: "pointer",
                animation: `fadeUp 0.3s ${i * 0.05}s ease both`,
              }}>
                <Avatar name={c.display_name} size={34} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 13, fontWeight: 600 }}>{c.display_name}</span>
                    {c.current_streak > 1 && <span style={{ fontSize: 11, color: "var(--warning)" }}>🔥{c.current_streak}</span>}
                    <span style={{ fontSize: 10, color: "var(--muted3)", marginLeft: "auto", fontFamily: "'DM Mono', monospace" }}>
                      {new Date(c.created_at || c.date).toLocaleTimeString("zh-TW", { hour: "2-digit", minute: "2-digit" })}
                    </span>
                  </div>
                  <p style={{ fontSize: 12, color: "var(--muted)", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.content}</p>
                </div>
              </div>
            ))}
            {data.today.length === 0 && <div style={{ padding: 20, textAlign: "center", fontSize: 13, color: "var(--muted2)" }}>今天還沒有打卡紀錄。</div>}
          </div>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div className="fade-up-1" style={{ background: "var(--card-bg)", border: "1px solid var(--border)", borderRadius: 16, overflow: "hidden" }}>
          <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>⚠️ 今日尚未打卡</span>
            <span style={{ background: "var(--danger-soft)", color: "var(--danger)", fontSize: 10, padding: "1px 6px", borderRadius: 10, fontWeight: 700 }}>{notCheckedInMembers.length}</span>
          </div>
          <div style={{ padding: "8px 0" }}>
            {notCheckedInMembers.map((m) => (
              <div key={m.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 16px" }}>
                <Avatar name={m.display_name} size={26} />
                <div style={{ flex: 1, fontSize: 12 }}>{m.display_name}</div>
                <div style={{ fontSize: 10, color: "var(--muted2)" }}>最近: {m.last_checkin_date ? m.last_checkin_date.slice(5) : "—"}</div>
              </div>
            ))}
            {notCheckedInMembers.length === 0 && <div style={{ padding: "10px 16px", fontSize: 12, color: "var(--muted2)" }}>太棒了，所有人都打卡了！</div>}
          </div>
        </div>

        <div className="fade-up-2" style={{ background: "var(--card-bg)", border: "1px solid var(--border)", borderRadius: 16, overflow: "hidden" }}>
          <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>📅 本週尚未打卡</span>
            <span style={{ background: notCheckedInThisWeek.length > 0 ? "var(--danger-soft)" : "var(--accent-soft)", color: notCheckedInThisWeek.length > 0 ? "var(--danger)" : "var(--accent)", fontSize: 10, padding: "1px 6px", borderRadius: 10, fontWeight: 700 }}>{notCheckedInThisWeek.length} 人</span>
          </div>
          <div style={{ padding: "8px 0" }}>
            {notCheckedInThisWeek.map((m) => (
              <div key={m.id} style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 16px" }}>
                <Avatar name={m.display_name} size={26} />
                <div style={{ flex: 1, fontSize: 12 }}>{m.display_name}</div>
                <div style={{ fontSize: 10, color: "var(--muted2)" }}>本週 0 天</div>
              </div>
            ))}
            {notCheckedInThisWeek.length === 0 && <div style={{ padding: "10px 16px", fontSize: 12, color: "var(--muted2)" }}>本週大家都有打卡！</div>}
          </div>
        </div>

        <div className="fade-up-2" style={{ background: "var(--card-bg)", border: "1px solid var(--accent-border)", borderRadius: 16, padding: 16 }}>
          <div style={{ fontSize: 11, color: "var(--accent)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 10, fontWeight: 700 }}>✨ 今日 AI 洞察</div>
          <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.7, marginBottom: 10 }}>
            今日打卡率 <span style={{ color: "var(--success)", fontWeight: 600 }}>({((data.today.length / (data.members.length || 1)) * 100).toFixed(0)}%)</span>。可到「AI 洞察」分頁取得 Gemini 分析。
          </div>
        </div>
      </div>
    </div>
  );
}

function AdminMembersTab({ data, TODAY }: { data: any, TODAY: string }) {
  const [sort, setSort] = useState("streak");
  const [search, setSearch] = useState("");

  const getSortValue = (m: any) =>
    sort === "streak" ? m.current_streak : sort === "total" ? m.total_checkins : m.this_week_checkins;

  const sorted = [...data.members].sort((a: any, b: any) => getSortValue(b) - getSortValue(a));

  const rankByMemberId: Record<string, number> = {};
  sorted.forEach((m: any, i: number) => {
    const val = getSortValue(m);
    if (val === 0) {
      rankByMemberId[m.id] = 0;
    } else {
      const sameAsPrev = i > 0 && val === getSortValue(sorted[i - 1]);
      rankByMemberId[m.id] = sameAsPrev ? rankByMemberId[sorted[i - 1].id]! : i + 1;
    }
  });

  const keyword = search.trim().toLowerCase();
  const filtered = keyword
    ? sorted.filter((m: any) =>
        (m.display_name || "").toLowerCase().includes(keyword)
      )
    : sorted;

  return (
    <div className="fade-up" style={{ background: "var(--card-bg)", border: "1px solid var(--border)", borderRadius: 16, overflow: "hidden" }}>
      <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>成員總覽</span>
        <span style={{ fontSize: 10, color: "var(--muted3)" }}>全部成員（含未打卡）</span>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <div style={{ display: "flex", gap: 6 }}>
            {[["streak", "連續"], ["week", "本週"], ["total", "累計"]].map(([v, l]) => (
              <button key={v} onClick={() => setSort(v)} style={{
                padding: "3px 10px", borderRadius: 6, border: "none", cursor: "pointer",
                fontSize: 11, fontFamily: "inherit",
                background: sort === v ? "var(--accent)" : "var(--card-bg-alt)",
                color: sort === v ? "white" : "var(--muted2)",
              }}>{l}</button>
            ))}
          </div>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="搜尋成員名稱..."
            style={{
              background: "var(--input-bg)",
              borderRadius: 999,
              border: "1px solid var(--border)",
              padding: "4px 10px",
              fontSize: 11,
              color: "var(--text)",
              outline: "none",
              minWidth: 140,
            }}
          />
        </div>
      </div>
      <div>
        <div style={{ display: "grid", gridTemplateColumns: "32px 1fr 80px 80px 80px 120px", gap: 8, padding: "8px 18px", borderBottom: "1px solid var(--card-bg-alt)" }}>
          {["", "成員", "本週", "累計", "連續", "近 7 天"].map((h, i) => (
            <div key={i} style={{ fontSize: 10, color: "var(--muted3)", textTransform: "uppercase", letterSpacing: "0.08em" }}>{h}</div>
          ))}
        </div>
        {filtered.length === 0 ? (
          <div style={{ padding: 20, textAlign: "center", fontSize: 13, color: "var(--muted2)" }}>
            {keyword ? "沒有符合的成員" : "尚無成員"}
          </div>
        ) : (
        filtered.map((m, i) => {
          const rank = rankByMemberId[m.id] ?? 0;
          const rankDisplay = rank === 0 ? "—" : rank === 1 ? "🥇" : rank === 2 ? "🥈" : rank === 3 ? "🥉" : rank;
          const checkedToday = data.today.find((c: any) => c.display_name === m.display_name || c.member_id === m.id);
          return (
            <div
              key={m.id}
              className="hoverable"
              onClick={() => {
                if (m.discord_id) {
                  window.open(`/?discord_id=${encodeURIComponent(m.discord_id)}`, "_blank");
                }
              }}
              style={{
              display: "grid", gridTemplateColumns: "32px 1fr 80px 80px 80px 120px",
              gap: 8, padding: "11px 18px", alignItems: "center", cursor: "pointer",
              borderBottom: i < filtered.length - 1 ? "1px solid var(--border)" : "none",
              animation: `fadeUp 0.3s ${i * 0.04}s ease both`,
            }}>
              <span style={{ fontSize: 13, color: "var(--muted3)", fontFamily: "'DM Mono', monospace" }}>
                {rankDisplay}
              </span>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Avatar name={m.display_name} size={26} />
                <span style={{ fontSize: 13 }}>{m.display_name}</span>
                {checkedToday && <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--success)", boxShadow: "0 0 5px var(--success)", display: "inline-block" }} />}
              </div>
              <span style={{ fontSize: 13, color: "var(--accent)", fontFamily: "'DM Mono', monospace" }}>{m.this_week_checkins}</span>
              <span style={{ fontSize: 13, color: "var(--muted)", fontFamily: "'DM Mono', monospace" }}>{m.total_checkins}</span>
              <span style={{ fontSize: 13, color: "var(--warning)", fontFamily: "'DM Mono', monospace" }}>{m.current_streak}🔥</span>
              <WeekDots member={m} today={TODAY} />
            </div>
          );
        })
        )}
      </div>
    </div>
  );
}

function AdminActivityTab({ data, TODAY }: { data: any, TODAY: string }) {
  const max = Math.max(...data.daily.map((d: any) => d.checkin_count), 1);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="fade-up" style={{ background: "var(--card-bg)", border: "1px solid var(--border)", borderRadius: 16, padding: "18px 20px" }}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 16 }}>每日打卡人數（過去 28 天）</div>
        <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height: 100 }}>
          {data.daily.slice(-28).map((d: any) => {
            const pct = d.checkin_count / max;
            const isToday = d.date === TODAY;
            return (
              <div key={d.date} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }} title={`${d.date}: ${d.checkin_count}人`}>
                <div style={{
                  width: "100%", borderRadius: "3px 3px 0 0",
                  height: `${Math.max(pct * 80, 4)}px`,
                  background: isToday ? "var(--accent)" : "var(--accent-soft)",
                  transition: "height 0.5s ease",
                  boxShadow: isToday ? "0 0 8px var(--accent-border)" : "none",
                }} />
              </div>
            );
          })}
        </div>
        {data.daily.length > 0 && (
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6 }}>
            <span style={{ fontSize: 10, color: "var(--muted3)" }}>{data.daily[0].date.slice(5)}</span>
            <span style={{ fontSize: 10, color: "var(--accent)" }}>今天</span>
          </div>
        )}
      </div>

      <div className="fade-up-1" style={{ background: "var(--card-bg)", border: "1px solid var(--border)", borderRadius: 16, padding: "18px 20px" }}>
        <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 16 }}>成員出勤預覽表（近 4 週）</div>
        <div style={{ display: "flex", gap: 8, overflowX: "auto" }}>
          {data.members.slice(0, 10).map((m: any) => {
            const dates = new Set(data.attendance?.[m.id] ?? []);
            return (
              <div key={m.id} style={{ minWidth: 90 }}>
                <div style={{ fontSize: 10, color: "var(--muted2)", marginBottom: 6, textAlign: "center" }}>{m.display_name}</div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 3 }}>
                  {Array.from({ length: 28 }, (_, i) => {
                    const d = new Date(TODAY);
                    d.setDate(d.getDate() - (27 - i));
                    const dateStr = d.toISOString().slice(0, 10);
                    const checked = dates.has(dateStr);
                    const isToday = dateStr === TODAY;
                    return (
                      <div
                        key={i}
                        title={`${dateStr}${checked ? " 有打卡" : ""}`}
                        style={{
                          width: 10,
                          height: 10,
                          borderRadius: 2,
                          background: checked ? "var(--success)" : "var(--border)",
                          opacity: checked ? (isToday ? 1 : 0.6 + (i / 28) * 0.4) : 1,
                          border: isToday ? "1px solid var(--border)" : "none",
                        }}
                      />
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function AdminInsightsTab({ week }: { week: number }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<{ type: string; title: string; content: string }[]>([]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        setLoading(true);
        setError(null);
        const res = await fetch("/api/insights");
        const body = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(body.error || "載入失敗，請稍後再試。");
        if (!cancelled) setItems(Array.isArray(body.items) ? body.items : []);
      } catch (e: any) {
        if (!cancelled) { console.error(e); setError(e.message || "載入失敗，請稍後再試。"); }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [week]);

  const colors: Record<string, string> = {
    alert: "var(--danger)",
    celebrate: "var(--success)",
    trend: "var(--accent)",
    risk: "var(--warning)",
    tip: "#7c3aed",
  };

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: 160, fontSize: 13, color: "var(--muted)" }}>
        正在向 Gemini 取得最新洞察…
      </div>
    );
  }

  if (error || items.length === 0) {
    return (
      <div style={{ fontSize: 13, color: "var(--muted)", background: "var(--card-bg)", borderRadius: 14, border: "1px solid var(--border)", padding: 16 }}>
        {error || "目前沒有可用的 AI 洞察，請稍後再試。"}
      </div>
    );
  }

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
      {items.map((ins, i) => {
        const color = colors[ins.type] || "var(--accent)";
        const icon = ins.type === "alert" ? "⚠️" : ins.type === "celebrate" ? "🎉" : ins.type === "risk" ? "🚩" : ins.type === "tip" ? "💡" : "📈";
        return (
          <div key={i} className="fade-up" style={{
            background: "var(--card-bg)", border: `1px solid ${color}30`,
            borderLeft: `3px solid ${color}`,
            borderRadius: 14, padding: 16,
            animation: `fadeUp 0.35s ${i * 0.07}s ease both`,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
              <span style={{ fontSize: 16 }}>{icon}</span>
              <span style={{ fontSize: 12, fontWeight: 700, color }}>{ins.title}</span>
            </div>
            <p style={{ fontSize: 13, color: "var(--muted)", lineHeight: 1.7 }}>{ins.content}</p>
          </div>
        );
      })}
    </div>
  );
}
