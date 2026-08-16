// 奇人库：所有异闻师的全部奇人与奇术。点击奇人跳转到其详情页
// （/admin/loadouts/:id，含全部信息与全部行迹）。

import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../api";
import { ChevronRightIcon } from "../../components/icons";
import type { AdminLoadout } from "./types";

export default function LoadoutBrowser() {
  const nav = useNavigate();
  const [loadouts, setLoadouts] = useState<AdminLoadout[]>([]);
  const [filter, setFilter] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    api<AdminLoadout[]>("/admin/loadouts")
      .then(setLoadouts)
      .catch((e: Error) => setErr(e.message));
  }, []);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return loadouts;
    return loadouts.filter(
      (l) => l.username?.toLowerCase().includes(q) || l.name.toLowerCase().includes(q)
    );
  }, [loadouts, filter]);

  return (
    <div className="admin-page">
      <div className="admin-toolbar">
        <div>
          <span className="eyebrow">LOADOUT LIBRARY</span>
          <h2>奇人库</h2>
        </div>
        <p className="muted">所有异闻师的全部奇人与奇术；点击奇人查看其详情与行迹</p>
      </div>
      {err && <p className="err">{err}</p>}

      <section className="panel">
        <div className="panel__head">
          <h3>奇人（{filtered.length}/{loadouts.length}）</h3>
          <input
            className="input"
            style={{ maxWidth: 260 }}
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="按异闻师 / 奇人名过滤…"
          />
        </div>
        <div className="tbl-list">
          {filtered.map((l) => (
            <div className="tbl-row" key={l.id}>
              <span className="tbl-col mono">#{l.id}</span>
              <span className="tbl-col tbl-col--main">
                <b>{l.name}</b>
                <small>{l.username ?? "（无主）"} · {l.style || "无风格"} · {l.enabled ? "已解封" : "未解封"}</small>
              </span>
              <span className="tbl-col">
                {l.abilities.length > 0 ? (
                  <span style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                    {l.abilities.map((a) => (
                      <span className="chip chip--ability" key={a.id} title={`${a.effect}${a.tactic ? `\n战术：${a.tactic}` : ""}`} style={{ fontSize: 12, padding: "3px 9px" }}>
                        {a.name}
                      </span>
                    ))}
                  </span>
                ) : (
                  <span className="muted">（无奇术）</span>
                )}
              </span>
              <span className="tbl-col mono">{l.battle_count} 场</span>
              <span className="tbl-col tbl-actions">
                <button
                  className="btn btn-ghost btn-icon btn-sm"
                  onClick={() => nav(`/admin/loadouts/${l.id}`)}
                  title="查看详情与行迹"
                >
                  <ChevronRightIcon size={14} />
                </button>
              </span>
            </div>
          ))}
        </div>
        {filtered.length === 0 && <p className="muted">{loadouts.length === 0 ? "暂无奇人。" : "无匹配奇人。"}</p>}
      </section>
    </div>
  );
}
