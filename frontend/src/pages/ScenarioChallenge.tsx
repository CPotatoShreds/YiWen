import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { streamEvents } from "../sse";

type View = "challenger" | "guardian" | "god";
type Stage = "loading" | "compare" | "ready" | "thinking" | "views";
type Message = {
  role: string;
  text?: string;
  challenger_text?: string;
  guardian_text?: string;
  omniscient?: string;
  created_at?: string;
};
type Challenge = {
  id: string;
  status: string;
  challenge_number: number;
  is_preview?: boolean;
  scenario: { id: string; name: string; background: string; victory_condition: string };
  roster: { character_name: string };
  challenger: { character_name: string };
  messages: Message[];
  guess_attempts: number;
  won: boolean | null;
  roster_id: string;
  viewer_role?: "challenger" | "owner";
};

const STAGE_TEXT: Record<Stage, string> = {
  loading: "正在接入小天下集",
  compare: "奇术比对中",
  ready: "比对完成，可以行动",
  thinking: "守方正在思考",
  views: "正在生成双方视角",
};

function viewText(message: Message, view: View) {
  if (view === "challenger") return message.challenger_text ?? (message.role === "guardian" ? message.text ?? "" : "");
  if (view === "guardian") return message.guardian_text ?? "";
  return message.omniscient ?? "";
}

export default function ScenarioChallenge() {
  const { id } = useParams<{ id: string }>();
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [text, setText] = useState("");
  const [guess, setGuess] = useState("");
  const [error, setError] = useState("");
  const [stage, setStage] = useState<Stage>("loading");
  const [view, setView] = useState<View>("challenger");
  const [liveGod, setLiveGod] = useState("");
  const [liveViews, setLiveViews] = useState<Record<"challenger" | "guardian", string>>({ challenger: "", guardian: "" });
  const [streamRetry, setStreamRetry] = useState(0);

  const load = () => id && api<Challenge>(`/scenario-challenges/${id}`).then((data) => {
    setChallenge(data);
    if (data.viewer_role === "owner") setView("guardian");
    setStage((current) => current === "loading" ? data.status === "active" ? "ready" : data.status === "preparing" || data.status === "failed" ? "compare" : "thinking" : current);
  }).catch((cause: Error) => setError(cause.message));

  useEffect(() => { void load(); }, [id]);

  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    let alive = true;
    let terminal = false;
    let reconnectTimer: number | undefined;
    const reconnect = () => {
      if (alive && !terminal) reconnectTimer = window.setTimeout(() => setStreamRetry((current) => current + 1), 1500);
    };
    void streamEvents(`/scenario-challenges/${id}/stream`, {
      onEvent: (event) => {
        if (event.type === "stage") {
          const next = event.stage as Stage;
          setStage(next);
          if (next === "ready") setChallenge((current) => current ? { ...current, status: "active" } : current);
          if (next === "thinking" || next === "views") setChallenge((current) => current ? { ...current, status: "resolving" } : current);
        } else if (event.type === "god") {
          setLiveGod(String(event.text ?? ""));
        } else if (event.type === "view_chunk") {
          const side = event.side as "challenger" | "guardian";
          if (side === "challenger" || side === "guardian") setLiveViews((current) => ({ ...current, [side]: current[side] + String(event.text ?? "") }));
        } else if (event.type === "turn") {
          const turn = event.turn as Message;
          setChallenge((current) => current && current.messages.some((message) => message.created_at === turn.created_at)
            ? current
            : current ? { ...current, messages: [...current.messages, turn], status: "active" } : current);
          setLiveGod("");
          setLiveViews({ challenger: "", guardian: "" });
        } else if (event.type === "error") {
          setError(String(event.message ?? "衍算未能完成"));
          const status = String(event.status ?? "active");
          setStage(status === "failed" ? "compare" : "ready");
          setChallenge((current) => current ? { ...current, status } : current);
        } else if (event.type === "done") {
          terminal = true;
        }
      },
      onClose: reconnect,
    }, controller.signal).catch(reconnect);
    return () => {
      alive = false;
      controller.abort();
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
    };
  }, [id, streamRetry]);

  const transcript = useMemo(() => challenge?.messages ?? [], [challenge]);
  const liveText = view === "god" ? liveGod : liveViews[view];
  const canAct = challenge?.status === "active" && stage === "ready" && challenge.won === null;
  const readOnly = challenge?.viewer_role === "owner";

  const act = async () => {
    if (!id || !text.trim() || !canAct) return;
    const outgoing: Message = { role: "challenger", text: text.trim(), created_at: `local-${Date.now()}` };
    setChallenge((current) => current ? { ...current, messages: [...current.messages, outgoing], status: "resolving" } : current);
    setStage("thinking");
    setError("");
    setText("");
    try {
      await api(`/scenario-challenges/${id}/actions`, { method: "POST", body: JSON.stringify({ text: outgoing.text }) });
    } catch (cause) {
      setChallenge((current) => current ? { ...current, messages: current.messages.filter((message) => message.created_at !== outgoing.created_at), status: "active" } : current);
      setStage("ready");
      setError(cause instanceof Error ? cause.message : "行动失败");
    }
  };

  const submitGuess = async () => {
    if (!id || !guess.trim()) return;
    try {
      await api(`/scenario-challenges/${id}/guess`, { method: "POST", body: JSON.stringify({ text: guess }) });
      setGuess("");
      void load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "猜词失败");
    }
  };

  const verify = async () => {
    if (!id) return;
    try {
      await api(`/scenario-challenges/${id}/guess/verify`, { method: "POST", body: JSON.stringify({ verified: true }) });
      void load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "验证失败");
    }
  };

  if (!challenge) return error ? <p className="err">{error}</p> : <div className="skeleton" style={{ height: 320 }} />;

  const viewLabel = view === "challenger" ? "挑战者视角" : view === "guardian" ? "守方视角" : "上帝视角";
  return <section className="panel world-story scenario-challenge">
    <div className="scenario-challenge__back"><Link className="muted" to={`/scenarios/${challenge.scenario.id}/rosters/${challenge.roster_id}`}>← 返回阵容详情</Link></div>
    <header className="world-story__head"><div><h1>{challenge.scenario.name}</h1><span className="muted">{challenge.is_preview ? "创作台试炼 · 不计入统计" : `第 ${challenge.challenge_number} 次挑战`}</span></div><span className={`scenario-stream-status is-${stage}`} aria-live="polite">{STAGE_TEXT[stage]}</span></header>
    <div className="world-story__brief"><p>{challenge.scenario.background}</p><p><strong>胜利条件：</strong>{challenge.scenario.victory_condition}</p></div>
    <nav className="scenario-view-tabs" role="tablist" aria-label="叙事视角">
      {!readOnly && <button type="button" role="tab" aria-selected={view === "challenger"} className={view === "challenger" ? "is-active" : ""} onClick={() => setView("challenger")}>{challenge.challenger.character_name}视角</button>}
      <button type="button" role="tab" aria-selected={view === "guardian"} className={view === "guardian" ? "is-active" : ""} onClick={() => setView("guardian")}>{challenge.roster.character_name}视角</button>
      {!readOnly && <button type="button" role="tab" aria-selected={view === "god"} className={view === "god" ? "is-active" : ""} onClick={() => setView("god")}>上帝视角</button>}
    </nav>
    <div className="world-transcript" aria-live="polite">
      {transcript.length === 0 && !liveText ? <div className="world-opening"><p>{stage === "compare" ? "双方奇术正在逐一比对。" : "比对完成后，写下第一步行动，让守方应对。"}</p></div> : transcript.map((message, index) => {
        if (message.role === "challenger") return <article className="world-message world-message--challenger" key={`${message.created_at}-${index}`}><span>挑战者行动</span><p>{message.text}</p></article>;
        const content = viewText(message, view);
        return content ? <article className={`world-message world-message--${view === "god" ? "god" : "guardian"}`} key={`${message.created_at}-${index}`}><span>{viewLabel}</span><p>{content}</p></article> : null;
      })}
      {liveText && <article className={`world-message world-message--${view === "god" ? "god" : "guardian"} is-streaming`}><span>{viewLabel}</span><p>{liveText}</p></article>}
      {stage === "thinking" && <div className="world-thinking">守方正在思考，异闻仍在衍算中。</div>}
    </div>
    {!readOnly && <><div className="world-composer"><textarea value={text} onChange={(event) => setText(event.target.value)} placeholder={canAct ? "写下下一步行动" : "等待本回合衍算完成"} disabled={!canAct} /><button className="btn btn-primary" disabled={!text.trim() || !canAct} onClick={() => void act()}>行动</button></div>
    <div className="world-composer scenario-guess-composer"><input className="input" value={guess} onChange={(event) => setGuess(event.target.value)} placeholder="猜测守方奇术" disabled={!canAct} /><button className="btn btn-ghost" disabled={!guess.trim() || !canAct} onClick={() => void submitGuess()}>提交猜词</button><button className="btn btn-ghost" disabled={!challenge.guess_attempts || !canAct} onClick={() => void verify()}>验证</button></div></>}
    {challenge.won && <p className="creator-notice">挑战成功</p>}
    {error && <p className="err">{error}</p>}
  </section>;
}
