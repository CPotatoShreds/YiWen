import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import MatchCard from "../components/MatchCard";
import { CheckIcon, ClockIcon, EyeIcon, LockIcon, SwordIcon, TargetIcon, TrophyIcon, XIcon } from "../components/icons";
import { Brush } from "../components/Ornaments";
import { streamEvents } from "../sse";

// SSE 重连退避参数：3s → 6s → 12s → … → 上限 30s，最多 10 次（耗尽显示「连接中断」手动续接）
const RETRY_BASE = 3000;
const RETRY_CAP_MS = 30000;
const MAX_RETRIES = 10;

interface AbilityLite {
  name: string;
  effect: string;
}
interface GuessCard {
  index: number;
  matched: string[];
  cracked: boolean;
  name?: string;
  effect?: string;
}
interface Battle {
  id: number;
  user_a: string;
  user_b: string;
  fighter_a: string;
  fighter_b: string;
  status: string;
  winner: string | null;
  rank_delta_a: number;
  rank_delta_b: number;
  share_token: string;
  share_token_b?: string;
  story: {
    narration_a?: string;
    narration_b?: string;
    abilities_a?: AbilityLite[];
    abilities_b?: AbilityLite[];
    insight_a?: string;
    insight_b?: string;
  } | null;
  can_guess: boolean;
  guessed: boolean;
  guess_hit: boolean | null;
  guess_score?: number;
  guess_by?: string | null;
  guess_history: string[];
  guess_text: string;
  guess_total: number;
  guess_cards?: GuessCard[] | null;
  guess_attempts_used: number;
  guess_attempts_max: number;
  revealed: boolean;
  friendly: boolean;
}

function AbilityList({ title, list, me, insight }: { title: string; list?: AbilityLite[]; me?: boolean; insight?: string }) {
  return (
    <div className="panel">
      <div className="panel__head">
        <h3>{me ? "我的奇术" : title}</h3>
        {!me && !list && <span className="muted" style={{ textAlign: "right" }}>尚未看破</span>}
      </div>
      {insight && (
        <p className="muted" style={{ fontSize: 13, marginBottom: 10, lineHeight: 1.6 }}>
          <b>解读：</b>{insight}
        </p>
      )}
      {!list ? (
        <div style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--muted)", fontSize: 13 }}>
          <LockIcon size={16} />
          对家奇术保密中——等败家猜奇术，猜中即被看破。
        </div>
      ) : (
        list.map((a, i) => (
          <div className="ability-item" key={i}>
            <div className="ability-item__body">
              <div className="ability-item__name">{a.name}</div>
              <p className="ability-item__effect">{a.effect}</p>
            </div>
          </div>
        ))
      )}
    </div>
  );
}

// 猜词空白卡片网格：进度条 + 线索片段 + 看破揭示（败方与赢家观战共用同一渲染）。
// 败方视角的片段由服务端按身份下发；赢家同样可见（双方看到的卡片数据一致）。
function GuessBoard({ cards }: { cards: GuessCard[] }) {
  return (
    <div className="guess-board" style={{ marginBottom: 14 }}>
      {cards.map((card) => (
        <div key={card.index} className={`guess-card ${card.cracked ? "guess-card--cracked" : ""}`}>
          <div className="guess-card__head">
            <span className="guess-card__no">第 {card.index} 门</span>
            {card.cracked ? (
              <span className="guess-card__label guess-card__label--hit">
                <CheckIcon size={13} /> 已看破
              </span>
            ) : (
              <span className="guess-card__label">
                <LockIcon size={13} /> 未知奇术
              </span>
            )}
          </div>
          {card.cracked ? (
            <div>
              <div className="guess-card__name">{card.name}</div>
              <p className="guess-card__effect">{card.effect}</p>
            </div>
          ) : (
            <>
              {card.matched.length > 0 && (
                <ul className="guess-card__matched">
                  {card.matched.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      ))}
    </div>
  );
}

// 猜测原文流：败方逐次道出的猜测（败方看自己的，赢家看对家的——交互感拉满）
function GuessFeed({ guesses }: { guesses: string[] }) {
  if (!guesses.length) return null;
  return (
    <ul className="guess-feed" style={{ marginBottom: 12 }}>
      {guesses.map((t, i) => (
        <li key={i}>{t}</li>
      ))}
    </ul>
  );
}

export default function BattleReport() {
  const { id } = useParams();
  const nav = useNavigate();
  const { user, refresh } = useAuth();
  const [b, setB] = useState<Battle | null>(null);
  const [err, setErr] = useState("");
  const [guessText, setGuessText] = useState("");
  const [guessing, setGuessing] = useState(false);
  const [liveSegments, setLiveSegments] = useState<string[]>([]);
  const [stage, setStage] = useState<"unknown" | "dueling" | "recounting">("unknown"); // SSE 推演进度：推演中（无标题）→ 正在对决中 → 胜负已分+奇人回归转写
  const [retry, setRetry] = useState(0); // 第几次重连（指数退避：3s→6s→…→上限30s）
  const [disconnected, setDisconnected] = useState(false); // 重连耗尽 → 显示「连接中断」+ 手动续接
  const [rematchBusy, setRematchBusy] = useState(false);
  const liveRoundRef = useRef(-1); // 已收最大分段轮次（断点去重：跨重连保留，服务端快照重播不重复）
  const stageRef = useRef<"unknown" | "dueling" | "recounting">("unknown"); // 进度单调游标：到「胜负已分」后不回退（重连快照会把 dueling 再重播一遍）
  const settledRef = useRef(false); // 已收 done/error → 不再重连保活，等 reload 拉完整话本
  const prevIdRef = useRef(id); // 上次加载的战场 id：切战场才清流式状态（StrictMode 双挂载/同 id 重访时不闪断已铺陈的内容）

  // 首次加载（推演中状态由下方流式 effect 接管；流失败时回退轮询刷新）
  useEffect(() => {
    // 切换战场（再来一场/另开一幡）：清空上一场的流式状态与断点游标；
    // 仅当 id 真的变了才清（StrictMode 双挂载 / 同 id 重访时不闪断已铺陈的内容）
    if (prevIdRef.current !== id) {
      prevIdRef.current = id;
      liveRoundRef.current = -1;
      stageRef.current = "unknown";
      settledRef.current = false;
      setLiveSegments([]);
      setStage("unknown");
      setDisconnected(false);
      setRetry(0);
    }
    let stopped = false;
    api<Battle>(`/battles/${id}`)
      .then((data) => {
        if (!stopped) setB(data);
      })
      .catch((e: any) => {
        if (!stopped) setErr(e.message);
      });
    return () => {
      stopped = true;
    };
  }, [id]);

  // 推演中 → SSE 流式拉取自己视角的分段转写；done/error 后重拉完整话本。
  // 断点续连：重连后服务端重播快照/续推，本地按轮次去重（liveRoundRef），不重复不丢段；
  // 连接中断按指数退避重连，耗尽则显示「连接中断」横幅等手动续接。
  useEffect(() => {
    if (!b || b.status !== "pending") return;
    let alive = true;
    const ctrl = new AbortController();
    let timer: number | undefined;
    const reload = () => {
      api<Battle>(`/battles/${id}`)
        .then((d) => {
          if (alive) setB(d);
        })
        .catch((e: any) => {
          if (alive) setErr(e.message);
        });
    };
    const reconnect = (immediate = false) => {
      if (!alive || settledRef.current) return; // 已收 done/error：不再重连保活，等 reload 拉完整话本
      if (retry >= MAX_RETRIES) {
        setDisconnected(true); // 重连耗尽：不再空转，等用户手动续接
        return;
      }
      const delay = Math.min(RETRY_BASE * 2 ** retry, RETRY_CAP_MS); // 3s→6s→12s→…→30s
      timer = window.setTimeout(() => setRetry((r) => r + 1), immediate ? 0 : delay);
    };
    streamEvents(
      `/battles/${id}/stream`,
      {
        onEvent: (ev) => {
          if (ev.type === "stage") {
            if (ev.stage === "recounting") {
              stageRef.current = "recounting";
              setStage("recounting");
            } else if (ev.stage === "dueling" && stageRef.current !== "recounting") {
              // 进度单调：已「胜负已分」后，重连快照重播的 dueling 一律忽略，不闪回「对决中」
              stageRef.current = "dueling";
              setStage("dueling");
            }
          } else if (ev.type === "segment") {
            const round = ev.round as number;
            if (round <= liveRoundRef.current) return; // 断点去重：快照重播/重复段跳过
            liveRoundRef.current = round;
            setLiveSegments((s) => [...s, ev.narration as string]);
          } else if (ev.type === "done" || ev.type === "error") {
            settledRef.current = true; // 已收尾 → 不再触发重连保活（避免 done 过渡期的重复订阅/快照重播）
            refresh(); // 结算后同步名望/见闻：导航栏数值即时浮出 ±N
            reload();
          }
        },
        onClose: reconnect, // 服务端关流（含意外断连）→ 重连保活
      },
      ctrl.signal,
    ).catch(() => reconnect(true)); // 连接失败/超时 → 立即进入退避重连
    return () => {
      alive = false;
      ctrl.abort();
      if (timer) clearTimeout(timer);
    };
  }, [id, b?.status, retry, refresh]);

  // 当前查看者是否为败方（猜词者）：逆转后 winner 会翻转，不能拿 winner 判断，用 guess_by。
  const isGuesser = b?.guess_by === user?.username;

  // 赢家视角实时看败方猜词：猜词进行中每 5s 轻量轮询刷新进度（败方每次提交后进度自动推进）。
  // 与上方 pending 的 SSE 流按 status 互斥；猜词结束（guessed）后停止轮询，落定显示。
  useEffect(() => {
    if (!b || b.status !== "done") return;
    if (isGuesser || b.guess_total <= 0 || b.guessed) return;
    const t = window.setInterval(() => {
      api<Battle>(`/battles/${id}`)
        .then(setB)
        .catch(() => {});
    }, 5000);
    return () => clearInterval(t);
  }, [id, b?.status, isGuesser, b?.guess_total, b?.guessed]);

  async function submitGuess() {
    if (!guessText.trim()) return;
    setGuessing(true);
    setErr("");
    try {
      const data = await api<Battle>(`/battles/${id}/guess`, {
        method: "POST",
        body: JSON.stringify({ text: guessText.trim() }),
      });
      setB(data);
      setGuessText("");
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setGuessing(false);
    }
  }

  async function rematch() {
    setRematchBusy(true);
    setErr("");
    try {
      const r = await api<{ id: number }>("/battles", { method: "POST" });
      nav(`/battles/${r.id}`);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setRematchBusy(false);
    }
  }

  if (err) return <p className="err">{err}</p>;
  if (!b) {
    return (
      <>
        <div className="skeleton" style={{ height: 150, marginBottom: 16 }} />
        <div className="skeleton" style={{ height: 240 }} />
      </>
    );
  }

  const me = user?.username;
  const mySide = b.user_a === me;

  if (b.status === "pending") {
    const myFighter = mySide ? b.fighter_a : b.fighter_b;
    return (
      <>
        <MatchCard userA={b.fighter_a} userB={b.fighter_b} subA={b.user_a} subB={b.user_b} status="pending" variant="hero" />
        <div className="banner banner--info" style={{ marginTop: 16 }}>
          <span className="banner__icon">
            <span className="brush-write">
              <Brush size={26} />
            </span>
          </span>
          <div>
            {stage === "recounting" ? (
              <>
                <h3>胜负已分</h3>
                <p>{myFighter} 正在返回异闻录……</p>
              </>
            ) : stage === "dueling" ? (
              <>
                <h3>正在对决中</h3>
                <p>双方奇人正于战场中对阵，胜负未分……</p>
              </>
            ) : (
              <p>书场初开，墨笔未落定前，先让故事铺陈一二……</p>
            )}
          </div>
        </div>
        {disconnected && (
          <div className="banner banner--info" style={{ marginTop: 12 }}>
            <span className="banner__icon">
              <ClockIcon size={20} />
            </span>
            <div>
              <h3>连接中断</h3>
              <p>与书场的连音断了，已铺陈的行迹没有丢失。点「续接」重连。</p>
            </div>
            <button
              className="btn btn-primary"
              style={{ marginLeft: "auto", whiteSpace: "nowrap" }}
              onClick={() => {
                setDisconnected(false);
                setRetry(0);
              }}
            >
              续接
            </button>
          </div>
        )}
        {liveSegments.length > 0 && (
          <div className="panel narration" style={{ marginTop: 16 }}>
            {liveSegments.join("\n\n")}
          </div>
        )}
      </>
    );
  }
  if (b.status === "failed") {
    const failStory = b.story as { error_message?: string; narration_a?: string; narration_b?: string } | null;
    const failMsg = failStory?.error_message || "铺陈败落，请回到书场重新启程。";
    const partial = mySide ? failStory?.narration_a ?? "" : failStory?.narration_b ?? "";
    return (
      <>
        <MatchCard userA={b.fighter_a} userB={b.fighter_b} subA={b.user_a} subB={b.user_b} status="failed" variant="hero" />
        <div className="banner banner--miss" style={{ marginTop: 16 }}>
          <span className="banner__icon">
            <XIcon size={20} />
          </span>
          <div>
            <h3>启程败落</h3>
            <p>{failMsg}</p>
          </div>
        </div>
        {partial && (
          <div className="panel narration" style={{ marginTop: 16 }}>
            {partial}
          </div>
        )}
        <div className="actions" style={{ marginTop: 20 }}>
          <button className="btn btn-primary btn-lg" onClick={rematch} disabled={rematchBusy}>
            <SwordIcon size={17} />
            {rematchBusy ? "摇签中…" : "再来一场"}
          </button>
          <button className="btn btn-ghost btn-lg" onClick={() => nav("/")}>
            返回
          </button>
        </div>
      </>
    );
  }
  if (!b.story) return <p className="muted">行迹为空。</p>;

  const fmt = (v: number) => (v > 0 ? `+${v}` : `${v}`);
  const myShareToken = mySide ? b.share_token : (b.share_token_b ?? b.share_token);
  const myAbilities = mySide ? b.story.abilities_a : b.story.abilities_b;
  const oppAbilities = mySide ? b.story.abilities_b : b.story.abilities_a;
  const myInsight = mySide ? b.story.insight_a : b.story.insight_b;
  const oppInsight = mySide ? b.story.insight_b : b.story.insight_a;
  const won = b.winner === me;
  const crackedCount = (b.guess_cards ?? []).filter((c) => c.cracked).length;

  return (
    <>
      {/* VS 头：签名时刻 */}
      <div className="rise">
        <MatchCard
          userA={b.fighter_a}
          userB={b.fighter_b}
          subA={b.user_a}
          subB={b.user_b}
          status="done"
          winner={b.winner}
          variant="hero"
          footer={
            <span>
              {b.friendly ? "切磋 · 不计名望" : `名望 ${b.user_a} ${fmt(b.rank_delta_a)} / ${b.user_b} ${fmt(b.rank_delta_b)}`}
            </span>
          }
        />
      </div>

      {/* 胜负结果 */}
      <div className="rise rise-1">
        {won ? (
          <div className="banner banner--hit">
            <span className="banner__icon">
              <TrophyIcon size={20} />
            </span>
            <div>
              <h3>你赢了这一场</h3>
              <p>胜者 {b.winner}，名望已入册。</p>
            </div>
          </div>
        ) : (
          <div className="banner banner--miss">
            <span className="banner__icon">
              <TargetIcon size={20} />
            </span>
            <div>
              <h3>{b.winner ? `胜者 ${b.winner}` : "和局"}</h3>
              <p>败而不馁，窥秘一刻——你获得了猜测对手奇术的机会。</p>
            </div>
          </div>
        )}
      </div>

      {/* 猜测结果（仅败方视角可见；赢家的收尾在下方赢家面板） */}
      {isGuesser && b.guessed && b.guess_total > 0 && (
        <div className={`banner rise rise-1 ${b.guess_hit ? "banner--hit" : "banner--miss"}`}>
          <span className="banner__icon">
            {b.guess_hit ? <CheckIcon size={20} /> : <XIcon size={20} />}
          </span>
          <div>
            <h3>
              {b.guess_hit
                ? "你识破了全部奇术，胜负逆转！"
                : "未看穿对家"}
            </h3>
            <p>
              {b.guess_hit
                ? "对家实际用过的奇术已被你尽数看破，反败为胜。"
                : `机会用尽，你道出的猜测：${b.guess_text || "（无）"}。`}
              {b.revealed ? " 双方奇术已尽数揭示。" : " 对家奇术仍未揭示。"}
            </p>
          </div>
        </div>
      )}

      {/* 战斗叙述：各看各的，服务端只回自己的视角叙述 */}
      <div className="panel narration rise rise-1">{b.story.narration_a ?? b.story.narration_b ?? "（无行迹内容）"}</div>

      {/* 奇术表 */}
      <div className="rise rise-2" style={{ display: "grid", gap: 14 }}>
        <AbilityList title={`${b.fighter_a} 的奇术`} list={myAbilities} me insight={myInsight} />
        <AbilityList title={`${b.fighter_b} 的奇术`} list={oppAbilities} insight={oppInsight} />
        {b.revealed && (
          <p className="muted" style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <EyeIcon size={14} /> 双方奇术已被看破
          </p>
        )}
      </div>

      {/* 猜奇术：空白卡片（仅败方视角；赢家观战面板见下方） */}
      {isGuesser && b.guess_total > 0 && (
        <div className="panel rise rise-3">
          <div className="panel__head">
            <h3>猜奇术：对家实际用过的奇术是什么？</h3>
          </div>
          <p className="muted" style={{ marginBottom: 12 }}>
            对家共动用 <b>{b.guess_total}</b> 门奇术。逐次道出你从行迹中看到的线索（允许意译），
            命中内容会落到对应卡片上；卡片被完整看透即看破该门奇术，全部看破即可逆转胜负。
          </p>

          <GuessFeed guesses={b.guess_history} />
          <GuessBoard cards={b.guess_cards ?? []} />

          {b.can_guess ? (
            <>
              <p className="muted" style={{ marginBottom: 10 }}>
                已用 <b>{b.guess_attempts_used}</b> / {b.guess_attempts_max} 次机会
                {b.guess_attempts_max - b.guess_attempts_used === 1 ? "（最后一次）" : ""}
              </p>
              <div className="field">
                <textarea
                  className="textarea"
                  value={guessText}
                  onChange={(e) => setGuessText(e.target.value)}
                  rows={3}
                  placeholder="如：他似乎能操控火焰，还能在近身时冻结我的兵刃……"
                />
              </div>
              <p className="muted" style={{ marginTop: 8, fontSize: 13 }}>
                支持同时对多个奇术进行猜测，请通过换行来分隔你对不同奇术的猜测。
              </p>
              <button className="btn btn-primary" onClick={submitGuess} disabled={guessing || !guessText.trim()}>
                <TargetIcon size={16} />
                {guessing ? "思量中…" : "道出猜测"}
              </button>
            </>
          ) : (
            <p className="muted">
              {b.guess_hit ? "你已看破全部奇术，胜负逆转。" : "猜测机会已用尽，未能尽数看破。"}
            </p>
          )}
          {err && <p className="err">{err}</p>}
        </div>
      )}

      {/* 赢家观战：实时看败方猜词进度（卡片进度/片段/看破 + 每次猜测原文，5s 轮询刷新） */}
      {!isGuesser && b.guess_total > 0 && (
        <div className="panel rise rise-3">
          <div className="panel__head">
            <h3>{b.guessed ? "对家猜奇术 · 已了结" : "对家正在猜你的奇术"}</h3>
          </div>
          <p className="muted" style={{ marginBottom: 12 }}>
            {b.guessed
              ? `对家道尽猜测：已用 ${b.guess_attempts_used} / ${b.guess_attempts_max} 次机会，看破 ${crackedCount} / ${b.guess_total} 门。${b.guess_hit ? "全破逆转，胜负改写！" : "未能全破。"}`
              : `对家正逐次道出猜测，看破你的奇术即揭示该门。已用 ${b.guess_attempts_used} / ${b.guess_attempts_max} 次机会，已看破 ${crackedCount} / ${b.guess_total} 门。`}
          </p>
          <GuessFeed guesses={b.guess_history} />
          <GuessBoard cards={b.guess_cards ?? []} />
        </div>
      )}

      {/* 传阅：分享的是自己的视角（A 分享 = A 视角，B 分享 = B 视角） */}
      <p className="muted" style={{ marginTop: 20 }}>
        传阅行迹（你的视角）：
        <a href={`/share/${myShareToken}`} target="_blank" rel="noreferrer">
          /share/{myShareToken}
        </a>
      </p>

      {/* 再来一场 / 返回 */}
      <div className="actions rise rise-4">
        <button className="btn btn-primary btn-lg" onClick={rematch} disabled={rematchBusy}>
          <SwordIcon size={17} />
          {rematchBusy ? "摇签中…" : "再来一场"}
        </button>
        <button className="btn btn-ghost btn-lg" onClick={() => nav("/")}>
          返回
        </button>
      </div>
    </>
  );
}
