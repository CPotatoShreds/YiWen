import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { BookIcon, CheckIcon, LockIcon, RefreshIcon, ScrollIcon, SwordIcon, TargetIcon, XIcon } from "../components/icons";
import { GuessClueCards } from "../components/GuessClueCards";
import type { CollectionChallenge, CollectionGuess, GuessCommentaryGroup } from "../types";

type Surface = "deduction" | "guess";

export default function CollectionChallengePage() {
  const { id } = useParams<{ id: string }>();
  const [challenge, setChallenge] = useState<CollectionChallenge | null>(null);
  const [selectedLineId, setSelectedLineId] = useState<number | null>(null);
  const [surface, setSurface] = useState<Surface>("deduction");
  const [action, setAction] = useState("");
  const [guess, setGuess] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => id && api<CollectionChallenge>(`/collections/challenges/${id}`).then(setChallenge).catch((error: Error) => setErr(error.message));
  useEffect(() => { load(); }, [id]);
  useEffect(() => {
    if (challenge && (selectedLineId === null || !challenge.worldlines.some((line) => line.id === selectedLineId))) {
      setSelectedLineId(challenge.worldlines.at(-1)?.id ?? null);
    }
  }, [challenge, selectedLineId]);

  const line = useMemo(
    () => challenge?.worldlines.find((item) => item.id === selectedLineId) ?? challenge?.worldlines.at(-1),
    [challenge, selectedLineId],
  );

  async function mutate(path: string, body?: unknown) {
    setBusy(true); setErr("");
    try { await api(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }); await load(); }
    catch (error: any) { setErr(error.message); }
    finally { setBusy(false); }
  }

  function sendAction(event: FormEvent) {
    event.preventDefault();
    if (line && action.trim()) { mutate(`/collections/worldlines/${line.id}/actions`, { text: action }); setAction(""); }
  }

  async function sendGuess(event: FormEvent) {
    event.preventDefault();
    if (!line || !guess.trim()) return;
    const text = guess.trim();
    setBusy(true); setErr("");
    try {
      const updated = await api<CollectionGuess>(`/collections/worldlines/${line.id}/guess`, { method: "POST", body: JSON.stringify({ text }) });
      setChallenge((current) => current ? { ...current, worldlines: current.worldlines.map((item) => item.id === line.id ? { ...item, guess: updated } : item) } : current);
      setGuess("");
      await load();
    } catch (error: any) { setErr(error.message); }
    finally { setBusy(false); }
  }

  async function verifyGuess() {
    if (!line) return;
    setBusy(true); setErr("");
    try {
      const updated = await api<CollectionGuess>(`/collections/worldlines/${line.id}/guess/verify`, { method: "POST" });
      setChallenge((current) => current ? { ...current, cracked: current.cracked || updated.cracked, worldlines: current.worldlines.map((item) => item.id === line.id ? { ...item, guess: updated } : item) } : current);
      await load();
    } catch (error: any) { setErr(error.message); }
    finally { setBusy(false); }
  }

  if (!challenge || !line) return err ? <p className="err">{err}</p> : <div className="skeleton" style={{ height: 420 }} />;

  const latest = challenge.worldlines.at(-1);
  const canAct = challenge.status === "active" && latest?.id === line.id && line.status === "active";
  const canRestart = challenge.status === "active" && !challenge.derived && latest?.status !== "active";
  const canGuess = challenge.status === "active" && !line.guess?.cracked;
  const pct = Math.min(100, Math.round((line.tokens_used / line.token_budget) * 100));
  const guessCards = (line.guess?.cards ?? []).map((card, index) => ({ ...card, index: index + 1 }));

  return <div className="collection-challenge-page">
    <div className="section-head"><h1 className="section-title"><ScrollIcon size={22} /> 衍算 · 第 {line.sequence} 世界</h1><Link className="muted" to="/collections">返回小天下集</Link></div>
    {err && <p className="err">{err}</p>}
    <div className="collection-play">
      <aside className="worldline-list panel"><header><h2>世界线</h2><p className="muted">旧线可回看，最新线可继续衍算。</p></header>{challenge.worldlines.map((item) => <button type="button" className={`worldline-list__item ${item.id === line.id ? "is-active" : ""}`} key={item.id} onClick={() => setSelectedLineId(item.id)}><b>第 {item.sequence} 世界</b><span>{item.status === "active" ? "推演中" : item.derived ? "已衍破" : "已封存"}</span></button>)}</aside>
      <main className="collection-main">
        <nav className="collection-surface-tabs" role="tablist" aria-label="推演方式">
          <button type="button" role="tab" aria-selected={surface === "deduction"} className={surface === "deduction" ? "is-active" : ""} onClick={() => setSurface("deduction")}><SwordIcon size={15} /> 衍算</button>
          <button type="button" role="tab" aria-selected={surface === "guess"} className={surface === "guess" ? "is-active" : ""} onClick={() => setSurface("guess")}><LockIcon size={15} /> 堪算{line.guess?.cracked ? " · 已破" : ""}</button>
        </nav>
        {surface === "deduction" ? <section className="world-story panel">
          <header className="world-story__head"><div><b>{challenge.challenger} 的点将</b><p className="muted">{challenge.derived ? "已衍破" : "未衍破"} · {challenge.cracked ? "已堪破" : "未堪破"}</p></div><div className="world-decay"><span>世界崩坏程度</span><progress value={line.tokens_used} max={line.token_budget} /><b>{pct}%</b></div></header>
          <div className="world-transcript">{line.messages.length === 0 ? <div className="world-opening"><BookIcon size={20} /><p>{challenge.opening}</p><small>写下第一步行动，让守场者应对。</small></div> : line.messages.map((message) => <div className={`world-message world-message--${message.role}`} key={message.id}><span>{message.role === "challenger" ? "你" : "守场"}</span><p>{message.text}</p></div>)}</div>
          {canAct ? <form className="world-composer" onSubmit={sendAction}><textarea value={action} onChange={(event) => setAction(event.target.value)} placeholder="写下你的行动…" maxLength={2000} /><button className="btn btn-primary" disabled={busy || !action.trim()}><SwordIcon size={15} /> 推进行动</button></form> : <div className="world-closed">{line.derived ? "此界已衍破，衍算封存，可继续堪算。" : line.id !== latest?.id ? "此为旧世界线，只可阅览。" : "此世界线已封存，不能再发送行动。"}</div>}
          <footer className="world-controls">{canAct && <><button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => mutate(`/collections/worldlines/${line.id}/derive`)}><CheckIcon size={14} /> 衍算检定</button><button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => mutate(`/collections/worldlines/${line.id}/end`)}><XIcon size={14} /> 封存回溯</button></>}{canRestart && <button className="btn btn-primary btn-sm" disabled={busy} onClick={() => mutate(`/collections/challenges/${challenge.id}/worldlines`)}><RefreshIcon size={14} /> 新开世界线</button>}<button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => mutate(`/collections/challenges/${challenge.id}/persist`)}><BookIcon size={14} /> 持久化点将阵容</button>{challenge.status === "active" && <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => mutate(`/collections/challenges/${challenge.id}/concede`)}><XIcon size={14} /> 结束挑战</button>}</footer>
        </section> : <GuessSurface guess={line.guess} cards={guessCards} active={canGuess} busy={busy} text={guess} setText={setGuess} onSubmit={sendGuess} onVerify={verifyGuess} />}
      </main>
    </div>
  </div>;
}

function GuessFeed({ guesses, comments }: { guesses: string[]; comments?: GuessCommentaryGroup[][] }) {
  if (!guesses.length) return null;
  return <ul className="guess-feed collection-guess-feed">{guesses.map((text, index) => {
    const groups = (comments?.[index] ?? []).filter((group) => group.index === 0);
    return <li key={index}><div>{text}</div>{groups.length > 0 && <div className="collection-guess-feed__comments">{groups.map((group) => <div key={group.index}>{group.index > 0 && <span className="collection-guess-feed__label">第 {group.index} 门：</span>}{group.items.map((item, itemIndex) => <span key={itemIndex}>「{item.text}」<span className="guess-feed__verdict">{item.verdict}</span>{itemIndex < group.items.length - 1 ? " · " : ""}</span>)}</div>)}</div>}</li>;
  })}</ul>;
}

function GuessSurface({ guess, cards, active, busy, text, setText, onSubmit, onVerify }: { guess: CollectionGuess | null; cards: Array<{ index: number; cracked: boolean; missing?: string; name?: string; effect?: string }>; active: boolean; busy: boolean; text: string; setText: (text: string) => void; onSubmit: (event: FormEvent) => void; onVerify: () => void }) {
  if (!guess) return <section className="collection-guess panel"><div className="collection-guess__empty"><LockIcon size={20} /><p>此视角暂未开放堪算。</p></div></section>;
  return <section className="collection-guess panel">
    <header className="collection-guess__head"><div><h2>猜奇术：守方实际用过的奇术是什么？</h2><p className="muted">守方共动用 <b>{guess.total}</b> 门奇术。逐次道出你从行迹中看到的线索，每次猜测都会得到一段点评；完成后主动发起检定。</p></div><span className={`collection-guess__status ${guess.cracked ? "is-done" : ""}`}>{guess.cracked ? "已全部看破" : `已获 ${guess.atom_count} 次原子评定`}</span></header>
    <GuessFeed guesses={guess.history} comments={guess.comments} />
    <GuessClueCards cards={cards} comments={guess.comments} />
    {active && !guess.cracked ? <><div className="field collection-guess__field"><textarea className="textarea" value={text} onChange={(event) => setText(event.target.value)} rows={3} placeholder="如：他似乎能操控火焰，还能在近身时冻结我的兵刃……" disabled={busy} /></div><div className="collection-guess__actions"><button className="btn btn-primary" onClick={onSubmit} disabled={busy || !text.trim()}><TargetIcon size={16} /> {busy ? "点评中…" : "道出猜测"}</button><button className="btn btn-ghost" onClick={onVerify} disabled={busy || !guess.can_verify} title={guess.can_verify ? "依据此前全部猜测与点评，验证各门奇术看破与否" : "需先道出新猜测并得到点评，才能发起检定"}><CheckIcon size={15} /> {busy ? "检定中…" : "检定"}</button></div></> : <p className="muted collection-guess__closed">{guess.cracked ? "你已看破全部守方奇术。" : "当前世界线不可继续堪算。"}</p>}
  </section>;
}
