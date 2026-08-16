// 管理端战报页：单场行迹的完整链路（讨论 / 三视角 / 猜词链路）+ 提示词方案调试对比。
// 调试对比：选一套提示词方案用 POST rerun 重跑本场（独立调试记录），展开与上方原版并列看差异。

import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../../api";
import { ChevronLeftIcon, TrashIcon } from "../../components/icons";
import type { PromptDebugRun, PromptScheme } from "./types";
import { fmtDt } from "./traceParsers";
import { BattleChainView, StoryView, TracePanel } from "./chainViews";

const RUN_LABEL: Record<string, string> = { pending: "推演中", done: "已落成", failed: "失手" };

function winnerLabel(side: string | null): string {
  return side === "A" ? "甲胜" : side === "B" ? "乙胜" : "和局";
}

function DebugPanel({ battleId }: { battleId: number }) {
  const [schemes, setSchemes] = useState<PromptScheme[]>([]);
  const [runs, setRuns] = useState<PromptDebugRun[]>([]);
  const [schemeId, setSchemeId] = useState<number | "">("");
  const [openRun, setOpenRun] = useState<number | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const loadRuns = () =>
    api<PromptDebugRun[]>(`/admin/prompt-debug-runs?battle_id=${battleId}`)
      .then(setRuns)
      .catch((e: Error) => setErr(e.message));

  useEffect(() => {
    api<PromptScheme[]>("/admin/prompt-schemes")
      .then(setSchemes)
      .catch((e: Error) => setErr(e.message));
    loadRuns();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [battleId]);

  // 有 pending 记录时轮询刷新，落定后停止
  const anyPending = runs.some((r) => r.status === "pending");
  useEffect(() => {
    if (!anyPending) return;
    const t = window.setInterval(loadRuns, 3000);
    return () => window.clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anyPending]);

  const enabled = schemes.filter((s) => s.enabled);

  async function rerun() {
    if (!schemeId) return;
    setBusy(true);
    setErr("");
    try {
      const run = await api<PromptDebugRun>(`/admin/battles/${battleId}/rerun`, {
        method: "POST",
        body: JSON.stringify({ scheme_id: Number(schemeId) }),
      });
      setRuns((prev) => [run, ...prev]);
      setOpenRun(run.id);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  }

  async function removeRun(run: PromptDebugRun) {
    if (!window.confirm(`确认删除这次重跑记录（方案「${run.scheme_name ?? "#" + run.scheme_id}」）？`)) return;
    try {
      await api(`/admin/prompt-debug-runs/${run.id}`, { method: "DELETE" });
      if (openRun === run.id) setOpenRun(null);
      await loadRuns();
    } catch (e: any) { setErr(e.message); }
  }

  return (
    <section className="panel debug-panel">
      <div className="panel__head">
        <h3>提示词方案调试</h3>
        <span className="muted">用不同方案重跑本场，对比三视角差异（独立调试记录，不进入玩家面）</span>
      </div>
      <div className="debug-rerun-bar">
        <select className="input" value={schemeId} onChange={(e) => setSchemeId(e.target.value ? Number(e.target.value) : "")}>
          <option value="">选择方案…</option>
          {enabled.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
        <button className="btn btn-primary btn-sm" disabled={!schemeId || busy} onClick={rerun}>
          {busy ? "创建中…" : "用此方案重跑"}
        </button>
        <button className="btn btn-ghost btn-sm" onClick={loadRuns}>刷新</button>
      </div>
      {enabled.length === 0 && <p className="muted">没有已启用的方案，先去「提示词方案」页创建。</p>}
      {err && <p className="err">{err}</p>}
      {runs.length === 0 && !err && <p className="muted">本场还没有调试记录。</p>}
      <div className="tbl-list">
        {runs.map((run) => {
          const open = openRun === run.id;
          return (
            <div className={`debug-run ${open ? "is-open" : ""}`} key={run.id}>
              <div className="tbl-row debug-run__row">
                <span className="tbl-col tbl-col--main">
                  <b>{run.scheme_name ?? `方案#${run.scheme_id}`}</b>
                  <small>
                    {RUN_LABEL[run.status] ?? run.status}
                    {run.status === "done" ? ` · ${winnerLabel(run.winner_side)}` : ""}
                  </small>
                </span>
                <span className="tbl-col mono">{fmtDt(run.created_at)}</span>
                <span className="tbl-col tbl-actions">
                  <button className="btn btn-ghost btn-sm" onClick={() => setOpenRun(open ? null : run.id)}>
                    {open ? "收起" : "查看"}
                  </button>
                  <button className="btn btn-danger btn-icon btn-sm" onClick={() => removeRun(run)} title="删除调试记录"><TrashIcon size={14} /></button>
                </span>
              </div>
              {open && (
                <div className="debug-run__body">
                  {run.status === "pending" && <p className="muted">推演进行中，链路可能不全…</p>}
                  {run.status === "failed" && <p className="err">重跑失手：{run.error}</p>}
                  {(run.status === "done" || run.status === "pending") && (
                    <>
                      <StoryView
                        story={run.story ?? null}
                        discussReport={run.discuss_report}
                        defaultTab="discuss"
                      />
                      <TracePanel battleId={run.id} kinds={["debug_rerun"]} />
                    </>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
      {openRun !== null && <p className="muted">展开的重跑与原版（上方）并列对照，可切换 讨论 / 上帝 / 甲 / 乙 页签。</p>}
    </section>
  );
}

export default function AdminBattleDetail() {
  const { id } = useParams();
  const nav = useNavigate();
  return (
    <div className="admin-page">
      <div className="admin-toolbar">
        <div>
          <span className="eyebrow">BATTLE REPORT</span>
          <h2>战报 #{id}</h2>
        </div>
        <div className="admin-toolbar__actions">
          <button className="btn btn-ghost" onClick={() => nav(-1)}>
            <ChevronLeftIcon size={14} /> 返回
          </button>
        </div>
      </div>
      <BattleChainView id={Number(id)} />
      <DebugPanel battleId={Number(id)} />
    </div>
  );
}
