/**
 * 【临时试验功能】奇术核心一句话试验：选奇术 → 生成核心一句话 → 逐条猜测比对。
 *
 * 与 app/api/routes/admin_core_guess.py 配套；纯试验用途，不落库、次数不限。
 * 删除时删本文件，并移除 App.tsx 中本页 import/路由一行、AdminLayout.tsx 导航一行、
 * 后端 admin_core_guess.py 路由文件及其在 router.py 的一行 include，即可删干净。
 */
import { useEffect, useState } from "react";
import { api } from "../../api";
import { CheckIcon, SwordIcon, XIcon } from "../../components/icons";
import type { Ability } from "./types";

interface CoreVerdict {
  hit_core: boolean;
  correct: string[];
  wrong: string[];
  missing: string[];
  verdict: string;
}

interface GuessEntry {
  text: string;
  result: CoreVerdict;
}

export default function CoreGuessLab() {
  const [abilities, setAbilities] = useState<Ability[]>([]);
  const [selected, setSelected] = useState("");
  const [coreDesc, setCoreDesc] = useState<string | null>(null);
  const [guessText, setGuessText] = useState("");
  const [guesses, setGuesses] = useState<GuessEntry[]>([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<Ability[]>("/admin/abilities")
      .then(setAbilities)
      .catch((e: Error) => setErr(e.message));
  }, []);

  async function enterTest() {
    if (!selected) return;
    setBusy(true);
    setErr("");
    setCoreDesc(null);
    setGuesses([]);
    try {
      const r = await api<{ core_desc: string }>("/admin/core-guess/describe", {
        method: "POST",
        body: JSON.stringify({ ability_id: selected }),
      });
      setCoreDesc(r.core_desc);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function submitGuess() {
    if (!coreDesc || !selected || !guessText.trim()) return;
    setBusy(true);
    setErr("");
    try {
      const r = await api<CoreVerdict>("/admin/core-guess/judge", {
        method: "POST",
        body: JSON.stringify({
          ability_id: selected,
          core_desc: coreDesc,
          user_guess: guessText,
        }),
      });
      setGuesses((g) => [...g, { text: guessText, result: r }]);
      setGuessText("");
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  const ability = abilities.find((a) => a.id === selected);

  return (
    <div className="admin-page">
      <div className="admin-toolbar">
        <div>
          <span className="eyebrow">CORE GUESS LAB</span>
          <h2>核心一句话试验</h2>
        </div>
        <p className="muted">临时测试功能：奇术 → 核心一句话 → 逐条猜测比对（次数不限，不落库玩家数据）</p>
      </div>
      {err && <p className="err">{err}</p>}

      <section className="panel">
        <div className="panel__head">
          <h3>选择奇术</h3>
          <span className="muted">从奇术库选一门，点击「进入测试」生成核心一句话描述</span>
        </div>
        <div className="admin-form-grid">
          <div className="field">
            <label>奇术</label>
            <select className="input" value={selected} onChange={(e) => setSelected(e.target.value)}>
              <option value="">选择奇术…</option>
              {abilities.map((a) => (
                <option key={a.id} value={a.id}>{a.name}：{a.effect}</option>
              ))}
            </select>
          </div>
        </div>
        {ability && (
          <div style={{ marginTop: 12, display: "grid", gap: 6 }}>
            <div><span className="muted">名称：</span><b>{ability.name}</b></div>
            <div><span className="muted">效果：</span>{ability.effect}</div>
            <div><span className="muted">补充说明：</span>{ability.detail || "（空）"}</div>
            <div><span className="muted">战术用法：</span>{ability.tactic || "（空）"}</div>
          </div>
        )}
        <div className="admin-toolbar__actions" style={{ marginTop: 4 }}>
          <button className="btn btn-primary" disabled={busy || !selected} onClick={enterTest}>
            <SwordIcon size={15} /> 进入测试
          </button>
          {coreDesc !== null && (
            <button className="btn btn-ghost" disabled={busy} onClick={() => { setCoreDesc(null); setGuesses([]); }}>
              重新开始
            </button>
          )}
        </div>
      </section>

      {coreDesc !== null && (
        <section className="panel">
          <div className="panel__head">
            <h3>核心一句话</h3>
            {ability && <span className="muted">{ability.name} · {ability.effect}</span>}
          </div>
          <p className="story-view__text" style={{ whiteSpace: "pre-wrap" }}>{coreDesc || "（生成结果为空）"}</p>
          <div className="admin-toolbar__actions" style={{ marginTop: 12 }}>
            <input
              className="input"
              style={{ flex: 1 }}
              value={guessText}
              onChange={(e) => setGuessText(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") submitGuess(); }}
              placeholder="道出你的猜测…（次数不限）"
            />
            <button className="btn btn-primary" disabled={busy || !guessText.trim()} onClick={submitGuess}>
              提交猜测
            </button>
          </div>

          {guesses.length > 0 && (
            <ul className="guess-feed" style={{ marginTop: 14 }}>
              {guesses.map((g, i) => (
                <li key={i} style={{ padding: "10px 0", borderBottom: "1px solid #eee" }}>
                  <div style={{ marginBottom: 4 }}>
                    <b>猜测 {i + 1}</b> {g.result.hit_core && <span className="status-chip status-chip--done">命中核心</span>}
                    <span className="muted"> · {g.text}</span>
                  </div>
                  <div style={{ color: g.result.hit_core ? "#1a7f37" : "#b35900" }}>
                    {g.result.hit_core ? <CheckIcon size={13} /> : <XIcon size={13} />}
                    {g.result.hit_core ? " 命中核心（猜词成功）" : " 未命中核心"}
                  </div>
                  <div style={{ marginTop: 2 }}>
                    说对：{g.result.correct.length ? g.result.correct.join("；") : "（无）"}
                    {" · "}说错：{g.result.wrong.length ? g.result.wrong.join("；") : "（无）"}
                  </div>
                  <div className="muted">遗漏：{g.result.missing.length ? g.result.missing.join("；") : "（无）"}</div>
                  <div className="muted">理由：{g.result.verdict}</div>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
