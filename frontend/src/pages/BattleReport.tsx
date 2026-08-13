import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError } from "../api";
import { useAuth } from "../auth";
import MatchCard from "../components/MatchCard";
import { CheckIcon, ClockIcon, EyeIcon, LockIcon, RefreshIcon, SwordIcon, TargetIcon, TrophyIcon, XIcon } from "../components/icons";
import { Brush } from "../components/Ornaments";
import { streamEvents } from "../sse";
import type { Battle, GuessCard } from "../types";

// SSE 重连退避参数：3s → 6s → 12s → … → 上限 30s，最多 10 次（耗尽显示「连接中断」手动续接）
const RETRY_BASE = 3000;
const RETRY_CAP_MS = 30000;
const MAX_RETRIES = 10;

interface AbilityLite {
  name: string;
  effect: string;
}

function AbilityList({ title, list, me }: { title: string; list?: AbilityLite[]; me?: boolean }) {
  return (
    <div className="panel">
      <div className="panel__head">
        <h3>{me ? "我的奇术" : title}</h3>
        {!me && !list && <span className="muted" style={{ textAlign: "right" }}>尚未看破</span>}
      </div>
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

// 连接中断横幅：SSE 重连耗尽时出现，点「续接」重置退避重新订阅（推演期与猜词期共用）
function DisconnectBanner({ onRetry }: { onRetry: () => void }) {
  return (
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
        onClick={onRetry}
      >
        续接
      </button>
    </div>
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
  const [confirmGiveUp, setConfirmGiveUp] = useState(false); // 收手二次确认：首次点击变「确认收手？」再点才提交
  const [viewTab, setViewTab] = useState<"own" | "god" | "opp">("own"); // 行迹视角标签：己方 / 上帝 / 对方
  const [contentTab, setContentTab] = useState<"abilities" | "guess">("abilities"); // 奇术与猜词标签
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
    if (!b) return;
    // 猜词阶段 = 已落定但有可猜的败方（guess_total>0 且未揭完）：与推演期共用总线，等 guess_done 回推
    const guessActive = b.status === "done" && (b.guess_total ?? 0) > 0 && !b.guessed;
    if (b.status !== "pending" && !guessActive) return;
    // 从推演期进入猜词阶段：推演已收尾标记作废，重连保活让位给猜词流
    if (guessActive && settledRef.current) {
      settledRef.current = false;
      setDisconnected(false);
      setRetry(0);
    }
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
          } else if (ev.type === "guess_done") {
            setGuessing(false); // 后台判定已落库：解锁输入，重拉含最新进度的行迹
            refresh();
            reload();
          } else if (ev.type === "guess_error") {
            setGuessing(false);
            setErr((ev.message as string) || "猜测判定失败，请稍后重试");
            reload();
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
  }, [id, b?.status, b?.guess_total, b?.guessed, retry, refresh]);

  // 标签页默认值：战场首次落定为 done 时设一次——我方可猜 → 落在「猜词」方便连续道出，否则「双方奇术」；
  // 同场重载（SSE 快照/guess_done 重拉）不重置用户手选；切换战场再按新场设默认。
  const tabInitKeyRef = useRef<string | null>(null);
  useEffect(() => {
    if (!b || b.status !== "done") return;
    const key = `${b.id}:${b.status}`;
    if (tabInitKeyRef.current === key) return;
    tabInitKeyRef.current = key;
    const guessing = b.can_guess && (b.my_guess?.total ?? 0) > 0;
    setContentTab(guessing ? "guess" : "abilities");
    setViewTab("own");
  }, [b?.id, b?.status, b?.can_guess, b?.my_guess?.total]);

  async function submitGuess() {
    if (!guessText.trim()) return;
    setConfirmGiveUp(false);
    setGuessing(true);
    setErr("");
    try {
      // 后端只做同步校验+受理（202），LLM 判定在后台任务跑，结果经 SSE guess_done 回推——
      // 短超时只等受理，不再像旧版同步链路那样被长判定掐断。
      await api<Battle>(`/battles/${id}/guess`, {
        method: "POST",
        body: JSON.stringify({ text: guessText.trim() }),
        timeout: 10000,
      });
      setGuessText("");
    } catch (e: any) {
      if (e instanceof ApiError && e.status === 409) {
        // 上一轮仍在判定中：静默忽略，等 SSE 回推
        return;
      }
      setErr(e.message);
      setGuessing(false);
    }
    // 兜底：若流中断没收到 guess_done，120s 后解锁输入，用户可重试
    window.setTimeout(() => setGuessing(false), 120000);
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

  // 再战：复刻本场（原快照 + 猜词进度）重新推演，一律切磋不计名望
  async function replay() {
    setRematchBusy(true);
    setErr("");
    try {
      const r = await api<{ id: number }>(`/battles/${id}/rematch`, { method: "POST" });
      nav(`/battles/${r.id}`);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setRematchBusy(false);
    }
  }

  // 收手：未看破即结束本轮猜词（是否揭示由被猜方 reveal_on_miss 决定）
  async function giveUp() {
    setConfirmGiveUp(false);
    setGuessing(true);
    setErr("");
    try {
      const d = await api<Battle>(`/battles/${id}/give-up`, { method: "POST" });
      setB(d);
      refresh(); // 和局恰一方全破时名望重算，同步导航栏数值
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setGuessing(false);
    }
  }

  if (!b) {
    if (err) return <p className="err">{err}</p>;
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
          <DisconnectBanner
            onRetry={() => {
              setDisconnected(false);
              setRetry(0);
            }}
          />
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
  const won = b.winner === me;
  const myGuess = b.my_guess ?? null;
  const oppGuess = b.opp_guess ?? null;
  const isGuesser = myGuess != null; // 我是猜词者：和局双方皆可猜，非和局仅败方
  const oppCracked = (oppGuess?.cards ?? []).filter((c) => c.cracked).length;
  const godView = b.story.narration; // 上帝视角：看破后才下发（点将局全破 / 双方看破揭示）
  const oppView = mySide ? b.story.narration_b : b.story.narration_a; // 对方视角：看破后才下发
  const ownView = mySide ? b.story.narration_a : b.story.narration_b;
  const hasGuess = (myGuess?.total ?? 0) > 0 || (oppGuess?.total ?? 0) > 0;

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
              {b.board_entry_id
                ? "点将局 · 奇人榜刻印 · 不计名望"
                : b.friendly
                  ? "切磋 · 不计名望"
                  : `名望 ${b.user_a} ${fmt(b.rank_delta_a)} / ${b.user_b} ${fmt(b.rank_delta_b)}`}
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

      {/* 猜词期连接中断横幅（推演期已有，done+未揭完时同样展示） */}
      {!b.guessed && b.guess_total > 0 && disconnected && (
        <DisconnectBanner
          onRetry={() => {
            setDisconnected(false);
            setRetry(0);
          }}
        />
      )}

      {/* 猜测结果（仅败方视角可见；赢家的收尾在下方赢家面板） */}
      {isGuesser && b.guessed && myGuess && myGuess.total > 0 && (
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

      {/* 点将局全部看破：无需猜词，完整三视角直接铺陈 */}
      {b.unlocked && (
        <div className="banner banner--hit rise rise-1">
          <span className="banner__icon">
            <EyeIcon size={20} />
          </span>
          <div>
            <h3>已全部看破，无需猜词</h3>
            <p>
              你已识破「{b.fighter_b}」刻印的全部奇术。此后点将这位奇人，行迹将直接以完整三视角铺陈——含上帝视角与刻印视角。
            </p>
          </div>
        </div>
      )}

      {/* 行迹视角：己方恒可见；上帝/对方视角看破后才解锁（看破前服务端不下发内容，标签也不渲染） */}
      <div className="rise rise-1" style={{ display: "grid", gap: 10 }}>
        <div className="tabs" role="tablist" aria-label="行迹视角">
          <button className={viewTab === "own" ? "is-active" : ""} onClick={() => setViewTab("own")}>
            己方视角
          </button>
          {godView && (
            <button className={viewTab === "god" ? "is-active" : ""} onClick={() => setViewTab("god")}>
              上帝视角
            </button>
          )}
          {oppView && (
            <button className={viewTab === "opp" ? "is-active" : ""} onClick={() => setViewTab("opp")}>
              对方视角
            </button>
          )}
        </div>
        <div className="panel narration" style={{ marginTop: 0, marginBottom: 0 }}>
          {viewTab === "god" ? godView : viewTab === "opp" ? oppView : (ownView ?? "（无行迹内容）")}
        </div>
      </div>

      {/* 奇术与猜词：标签页分开（猜词标签仅在有内容时出现；双方奇术看破前按各自视角保密） */}
      <div className="rise rise-2" style={{ display: "grid", gap: 12 }}>
        <div className="tabs" role="tablist" aria-label="奇术与猜词">
          <button className={contentTab === "abilities" ? "is-active" : ""} onClick={() => setContentTab("abilities")}>
            双方奇术
          </button>
          {hasGuess && (
            <button className={contentTab === "guess" ? "is-active" : ""} onClick={() => setContentTab("guess")}>
              猜词
            </button>
          )}
        </div>

        {contentTab === "guess" && hasGuess ? (
          <div style={{ display: "grid", gap: 14 }}>
            {isGuesser && myGuess && myGuess.total > 0 && (
              <div className="panel" style={{ marginBottom: 0 }}>
                <div className="panel__head">
                  <h3>猜奇术：对家实际用过的奇术是什么？</h3>
                </div>
                <p className="muted" style={{ marginBottom: 12 }}>
                  对家共动用 <b>{myGuess.total}</b> 门奇术。逐次道出你从行迹中看到的线索（允许意译），
                  命中内容会落到对应卡片上；卡片被完整看透即看破该门奇术，全部看破即可逆转胜负。
                </p>

                <GuessFeed guesses={myGuess.history} />
                <GuessBoard cards={myGuess.cards ?? []} />

                {b.can_guess ? (
                  <>
                    <p className="muted" style={{ marginBottom: 10 }}>
                      已用 <b>{myGuess.attempts_used}</b> / {myGuess.attempts_max} 次机会，已看破{" "}
                      {(myGuess.cards ?? []).filter((c) => c.cracked).length} / {myGuess.total} 门。
                    </p>
                    <div className="field">
                      <textarea
                        className="textarea"
                        value={guessText}
                        onChange={(e) => {
                          setGuessText(e.target.value);
                          setConfirmGiveUp(false);
                        }}
                        rows={3}
                        placeholder="如：他似乎能操控火焰，还能在近身时冻结我的兵刃……"
                      />
                    </div>
                    <p className="muted" style={{ marginTop: 8, fontSize: 13 }}>
                      支持同时对多个奇术进行猜测，请通过换行来分隔你对不同奇术的猜测。
                    </p>
                    <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                      <button className="btn btn-primary" onClick={submitGuess} disabled={guessing || !guessText.trim()}>
                        <TargetIcon size={16} />
                        {guessing ? "思量中…" : "道出猜测"}
                      </button>
                      <button
                        className={`btn ${confirmGiveUp ? "btn-danger" : "btn-ghost"}`}
                        onClick={() => (confirmGiveUp ? giveUp() : setConfirmGiveUp(true))}
                        disabled={guessing}
                        title="未看破即结束本轮猜词，之后不可再猜"
                      >
                        <XIcon size={15} />
                        {confirmGiveUp ? "确认收手？" : "收手"}
                      </button>
                    </div>
                  </>
                ) : (
                  <p className="muted">
                    {myGuess.flipped ? "你已看破全部奇术，胜负逆转。" : "你已收手或机会用尽，未能尽数看破。"}
                  </p>
                )}
                {err && <p className="err">{err}</p>}
              </div>
            )}

            {oppGuess && oppGuess.total > 0 && (
              <div className="panel" style={{ marginBottom: 0 }}>
                <div className="panel__head">
                  <h3>{b.guessed ? "对家猜奇术 · 已了结" : "对家正在猜你的奇术"}</h3>
                </div>
                <p className="muted" style={{ marginBottom: 12 }}>
                  {b.guessed
                    ? `对家道尽猜测：已用 ${oppGuess.attempts_used} / ${oppGuess.attempts_max} 次机会，看破 ${oppCracked} / ${oppGuess.total} 门。${oppGuess.flipped ? "全破逆转，胜负改写！" : "未能全破。"}`
                    : `对家正逐次道出猜测，看破你的奇术即揭示该门。已用 ${oppGuess.attempts_used} / ${oppGuess.attempts_max} 次机会，已看破 ${oppCracked} / ${oppGuess.total} 门。`}
                </p>
                <GuessFeed guesses={oppGuess.history} />
                <GuessBoard cards={oppGuess.cards ?? []} />
              </div>
            )}
          </div>
        ) : (
          <div style={{ display: "grid", gap: 14 }}>
            <AbilityList title={`${b.fighter_a} 的奇术`} list={myAbilities} me />
            <AbilityList title={`${b.fighter_b} 的奇术`} list={oppAbilities} />
            {b.revealed && (
              <p className="muted" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <EyeIcon size={14} /> 双方奇术已被看破
              </p>
            )}
          </div>
        )}
      </div>

      {/* 传阅：分享的是自己的视角（A 分享 = A 视角，B 分享 = B 视角） */}
      <p className="muted" style={{ marginTop: 20 }}>
        传阅行迹（你的视角）：
        <a href={`/share/${myShareToken}`} target="_blank" rel="noreferrer">
          /share/{myShareToken}
        </a>
      </p>

      {/* 再战（复刻本场）/ 再来一场（随机新局）/ 返回；点将局不可再战，进度自会跨场累积 */}
      <div className="actions rise rise-4">
        {!b.board_entry_id && (
          <button className="btn btn-primary btn-lg" onClick={replay} disabled={rematchBusy}>
            <RefreshIcon size={17} />
            {rematchBusy ? "复刻中…" : "再战"}
          </button>
        )}
        <button className="btn btn-ghost btn-lg" onClick={rematch} disabled={rematchBusy}>
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
