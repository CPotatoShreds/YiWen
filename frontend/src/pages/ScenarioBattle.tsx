import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { streamEvents } from "../sse";
import { startScenarioChallenge } from "../scenarioChallenge";
import { SealStamp } from "../components/Ornaments";
import { BookIcon, RefreshIcon, XIcon } from "../components/icons";
import { ScenarioManuscript } from "../components/ScenarioNarrative";
import { BackButton } from "../components/PageShell";
import {
  STAGE_STEPS,
  STAGE_TEXT,
  chineseNumber,
  isInProgress,
  type Message,
  type ScenarioHistoryItem,
  type Stage,
} from "../scenarioModel";
import type { Character } from "../types";

type Scenario = {
  id: string;
  slug: string;
  name: string;
  subtitle: string;
  introduction: string;
  background: string;
  rules: string[];
  victory_condition: string;
  judgement_rules: string[];
};
type RosterContext = {
  scenario: Scenario;
  roster: {
    character_name: string;
    character_bio: string;
    ability_count: number;
    challenger_win_rate: number | null;
  };
  viewer_role?: "challenger" | "owner";
  my_progress?: { attempts: number; cracked_cards: { index: number; cracked: boolean }[] } | null;
  my_challenges: ScenarioHistoryItem[];
};
type Challenge = {
  id: string;
  status: string;
  challenge_number: number;
  is_preview?: boolean;
  scenario: Scenario;
  roster: { character_name: string };
  challenger: { character_id?: string; character_name: string };
  messages: Message[];
  won: boolean | null;
  roster_id: string;
  viewer_role?: "challenger" | "owner";
  god_unlocked?: boolean;
  derived?: { comparison_report?: string; achieved?: boolean; reason?: string };
};
type Ability = { id: string; name: string };

const ORDER: Record<Stage, number> = {
  loading: 0,
  compare: 1,
  ready: 2,
  thinking: 3,
  views: 4,
  result: 5,
};

/** 挑战状态 → 阶段推导（初载与轮询共用；细阶段由 SSE 事件到达推进）。 */
const stageFromStatus = (status: string): Stage =>
  status === "preparing"
    ? "compare"
    : status === "resolving"
      ? "thinking"
      : status === "won" || status === "lost"
        ? "result"
        : "ready";

/**
 * 对战页：归属异闻（擂台）的常驻地址，起笔前后的唯一对战页面。
 * 两段式：起笔前是「对决信息 + 操作台」，点「发起推演」后整页换成「行迹书页」。
 * 单主视角（推演遮挡块 → 己方叙述正文）；往期记录在独立的记录阅读页。
 */
export default function ScenarioBattle() {
  const { scenarioSlug, rosterId } = useParams<{ scenarioSlug: string; rosterId: string }>();
  const [context, setContext] = useState<RosterContext | null>(null);
  const [characters, setCharacters] = useState<Character[] | null>(null);
  const [abilities, setAbilities] = useState<Ability[] | null>(null);
  const [contextToken, setContextToken] = useState(0);
  const [characterId, setCharacterId] = useState("");
  const [strategy, setStrategy] = useState("");
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [stage, setStage] = useState<Stage>("loading");
  const [view, setView] = useState<"booting" | "draft" | "book">("booting");
  const [liveDeduction, setLiveDeduction] = useState("");
  const [liveOwn, setLiveOwn] = useState("");
  const [streamRetry, setStreamRetry] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const ownSideRef = useRef<"challenger" | "guardian">("challenger");
  const bootedFor = useRef<string | null>(null);
  const startedHere = useRef(false);
  const lastNumber = useRef(0);
  const pendingDerive = useRef(false);
  const deriveRef = useRef<() => void>(() => {});

  // 异闻上下文（擂台）与自家奇人
  useEffect(() => {
    if (!scenarioSlug || !rosterId) return;
    let alive = true;
    api<RosterContext>(`/scenarios/${scenarioSlug}/rosters/${rosterId}`)
      .then((data) => alive && setContext(data))
      .catch((cause: Error) => alive && setError(cause.message));
    return () => {
      alive = false;
    };
  }, [scenarioSlug, rosterId, contextToken]);

  // 自家奇人与奇术名（后者只用于人物榜的招式摘要，取不到就退化为 —）
  useEffect(() => {
    let alive = true;
    Promise.allSettled([api<Character[]>("/creator/characters"), api<Ability[]>("/creator/abilities")]).then(
      ([self, arts]) => {
        if (!alive) return;
        setCharacters(self.status === "fulfilled" ? self.value : []);
        setAbilities(arts.status === "fulfilled" ? arts.value : []);
      },
    );
    return () => {
      alive = false;
    };
  }, []);

  // 首屏若这座擂台上有未终局的回合，直接续上；没有就停在新局
  useEffect(() => {
    if (!context || !rosterId || bootedFor.current === rosterId) return;
    bootedFor.current = rosterId;
    const live = context.my_challenges.find((item) => isInProgress(item.status));
    if (live) {
      setCharacterId(live.challenger_character_id ?? "");
      setCurrentId(live.id);
      return;
    }
    setView("draft");
  }, [context, rosterId]);

  // 载入当前回合并订阅实时行迹
  useEffect(() => {
    if (!currentId) {
      setChallenge(null);
      setStage("loading");
      return;
    }
    let alive = true;
    setChallenge(null);
    setStage("loading");
    api<Challenge>(`/scenario-challenges/${currentId}`)
      .then((data) => {
        if (!alive) return;
        setChallenge(data);
        lastNumber.current = data.challenge_number;
        ownSideRef.current = data.viewer_role === "owner" ? "guardian" : "challenger";
        const next: Stage = stageFromStatus(data.status);
        setStage((current) => (ORDER[next] >= ORDER[current] || current === "loading" ? next : current));
        const prior = data.messages.find((message) => message.role === "challenger");
        if (prior) setStrategy(prior.text ?? "");
        if (data.status === "failed") {
          startedHere.current = false;
          pendingDerive.current = false;
          setView("draft");
          return;
        }
        // 已进入推演/终局，或策略已落库 → 书页；尚在比对且不是本会话起笔的（刷新续局）→ 操作台
        if (prior || data.status === "resolving" || data.status === "won" || data.status === "lost") setView("book");
        else setView(startedHere.current ? "book" : "draft");
      })
      .catch((cause: Error) => alive && setError(cause.message));
    return () => {
      alive = false;
    };
  }, [currentId]);

  useEffect(() => {
    if (!currentId) return;
    const controller = new AbortController();
    let alive = true;
    let terminal = false;
    let retryTimer: number | undefined;
    const reconnect = () => {
      if (alive && !terminal)
        retryTimer = window.setTimeout(() => setStreamRetry((value) => value + 1), 1500);
    };
    void streamEvents(
      `/scenario-challenges/${currentId}/stream`,
      {
        onEvent: (event) => {
          if (event.type === "deduction_progress") {
            // 推演遮挡流：只收到累计字数，前端按字数合成遮挡符号（真实文本不出站）
            // 密度 1 符 / 20 字、上限 240 符——稳定增长且不撑爆版面
            const chars = Number(event.chars ?? 0);
            setLiveDeduction("❖".repeat(Math.min(240, Math.max(1, Math.ceil(chars / 20)))));
            setStage((current) => (ORDER["thinking"] >= ORDER[current] ? "thinking" : current));
          } else if (event.type === "narration_snapshot") {
            // 断线重连补发：服务端累计全文整体替换（修复重连后中间缺段/叙述重流叠字）
            if (event.side === ownSideRef.current) setLiveOwn(String(event.text ?? ""));
            setStage((current) => (ORDER["views"] >= ORDER[current] ? "views" : current));
          } else if (event.type === "narration_chunk") {
            // 服务端已按侧别过滤：本连接只会收到己方叙述
            if (event.side === ownSideRef.current) setLiveOwn((current) => current + String(event.text ?? ""));
            setStage((current) => (ORDER["views"] >= ORDER[current] ? "views" : current));
          } else if (event.type === "turn") {
            const turn = event.turn as Message;
            setChallenge((current) =>
              current && current.messages.some((message) => message.created_at === turn.created_at)
                ? current
                : current
                  ? { ...current, messages: [...current.messages, turn] }
                  : current,
            );
            setLiveDeduction("");
            setLiveOwn("");
          } else if (event.type === "error") {
            // 流已判死：先停重连，再退回操作台让玩家带着原策略重试
            terminal = true;
            pendingDerive.current = false;
            setError(String(event.message ?? "推演未能完成"));
            setStage("compare");
            setView("draft");
            setChallenge((current) => (current ? { ...current, status: "failed" } : current));
          } else if (event.type === "done") terminal = true;
        },
        onClose: reconnect,
      },
      controller.signal,
    ).catch(reconnect);
    return () => {
      alive = false;
      controller.abort();
      if (retryTimer) window.clearTimeout(retryTimer);
    };
  }, [currentId, streamRetry]);

  // 回合终局后刷新记录列表（记录阅读页里应立刻出现这一场）
  const runStatus = challenge?.status ?? "";
  useEffect(() => {
    if (runStatus === "won" || runStatus === "lost" || runStatus === "failed")
      setContextToken((value) => value + 1);
  }, [runStatus]);

  // 状态轮询：比对期/推演期每 2s 刷新详情——细阶段由 SSE 事件推进，
  // 轮询负责状态同步（比对完成→可提策略）与终局过渡（won/lost→结果面板），终态自动停。
  useEffect(() => {
    if (!currentId || (runStatus !== "preparing" && runStatus !== "resolving")) return;
    let alive = true;
    let timer: number | undefined;
    const tick = async () => {
      try {
        const data = await api<Challenge>(`/scenario-challenges/${currentId}`);
        if (!alive) return;
        setChallenge(data);
        const next: Stage = stageFromStatus(data.status);
        setStage((current) => (ORDER[next] >= ORDER[current] || current === "loading" ? next : current));
      } catch {
        // 静默：网络抖动下轮再试
      }
      if (alive) timer = window.setTimeout(() => void tick(), 2000);
    };
    timer = window.setTimeout(() => void tick(), 2000);
    return () => {
      alive = false;
      if (timer) window.clearTimeout(timer);
    };
  }, [currentId, runStatus]);

  const canSubmitStrategy =
    !!challenge && challenge.status === "active" && challenge.won === null && stage === "ready";
  // 从操作台发起的：比对完成的那一刻自动提交策略，免二次点击
  useEffect(() => {
    if (view !== "book" || !pendingDerive.current || !canSubmitStrategy) return;
    pendingDerive.current = false;
    deriveRef.current();
  }, [view, canSubmitStrategy]);

  // 仅装配 1-4 门奇术的自家奇人可出战（与后端 _character_snapshot 的约束一致）
  const available = useMemo(
    () => (characters ?? []).filter((c) => c.ability_ids.length >= 1 && c.ability_ids.length <= 4),
    [characters],
  );
  const abilityNames = useMemo(
    () => new Map((abilities ?? []).map((item) => [item.id, item.name])),
    [abilities],
  );

  if (!context)
    return error ? <p className="err">{error}</p> : <div className="skeleton" style={{ height: 320 }} />;

  const failed = challenge?.status === "failed";
  const owner = challenge?.viewer_role === "owner" || context.viewer_role === "owner";
  const own: "challenger" | "guardian" = owner ? "guardian" : "challenger";
  const ownLabel = owner
    ? context.roster.character_name
    : (challenge?.challenger.character_name ?? available.find((c) => c.id === characterId)?.name ?? "");
  const preview = context.viewer_role === "owner" || !!challenge?.is_preview;
  const backHref = `/scenarios/${scenarioSlug}/rosters/${rosterId}`;
  const recordsHref = `${backHref}/records`;

  const cards = context.my_progress?.cracked_cards ?? [];
  const cracked = cards.filter((card) => card.cracked).length;
  const abilityTotal = context.roster.ability_count || cards.length;
  const winRate =
    context.roster.challenger_win_rate == null
      ? "暂无胜负"
      : `挑战者胜率 ${Math.round(context.roster.challenger_win_rate * 100)}%`;
  const attempts = context.my_progress?.attempts ?? 0;
  // 新局的场次：/scenarios 有 10s 缓存，用「已推演次数」与本会话见过的最大场次兜底，页码不回退
  const nextRun = Math.max(attempts + 1, lastNumber.current + 1);
  const runNumber = challenge?.challenge_number ?? nextRun;
  // 已起笔但策略未落库：人物榜锁住，只改策略
  const locked = !!currentId && !challenge?.messages.some((message) => message.role === "challenger") && !failed;

  const artsOf = (character: Character) => {
    const names = character.ability_ids
      .map((id) => abilityNames.get(id))
      .filter((name): name is string => !!name);
    if (!names.length) return character.ability_ids.length ? `${character.ability_ids.length} 门` : "—";
    const head = names.slice(0, 2).join(" / ");
    return names.length > 2 ? `${head} +${names.length - 2}` : head;
  };

  const scrollTop = () => window.scrollTo({ top: 0 });

  const begin = async () => {
    if (!rosterId || !characterId || busy) return;
    startedHere.current = true;
    // 乐观切页：立刻换成书页，比对期由书页显示已写下的策略
    setView("book");
    setChallenge(null);
    setStage("loading");
    setLiveDeduction("");
    setLiveOwn("");
    setError("");
    setBusy(true);
    try {
      const id = await startScenarioChallenge(rosterId, characterId);
      pendingDerive.current = true;
      setCurrentId(id);
      scrollTop();
    } catch (cause) {
      startedHere.current = false;
      setView("draft");
      setError(cause instanceof Error ? cause.message : "起笔失败");
    } finally {
      setBusy(false);
    }
  };

  const derive = async () => {
    if (!currentId || !canSubmitStrategy) return;
    setError("");
    setStage("thinking");
    setView("book");
    setChallenge((current) => (current ? { ...current, status: "resolving" } : current));
    try {
      await api(`/scenario-challenges/${currentId}/derive`, {
        method: "POST",
        body: JSON.stringify({ strategy: strategy.trim() }),
      });
    } catch (cause) {
      // 服务端可能已收下这次提交（双击/重连竞态）：先以详情为准，再决定回操作台还是留在书页
      setError(cause instanceof Error ? cause.message : "推演启动失败");
      try {
        const data = await api<Challenge>(`/scenario-challenges/${currentId}`);
        setChallenge(data);
        const next = stageFromStatus(data.status);
        setStage(next);
        if (data.status === "resolving" || data.status === "won" || data.status === "lost") {
          pendingDerive.current = false;
          setView("book");
          return;
        }
      } catch {
        // 详情也取不到：把乐观改写的 resolving 撤回，保证操作台能再次提交
        setStage("ready");
        setChallenge((current) => (current ? { ...current, status: "active" } : current));
      }
      pendingDerive.current = false;
      setView("draft");
    }
  };

  // 再战：清空当前回合但不离开擂台，沿用本场的奇人与策略
  const restart = () => {
    if (challenge) setCharacterId(challenge.challenger.character_id ?? characterId);
    startedHere.current = false;
    pendingDerive.current = false;
    setLiveDeduction("");
    setLiveOwn("");
    setError("");
    setCurrentId(null);
    setStage("loading");
    setView("draft");
    scrollTop();
  };

  deriveRef.current = derive;

  const submitLabel = locked
    ? canSubmitStrategy
      ? "开始推演"
      : stage === "compare"
        ? "奇术比对中…"
        : "等待比对"
    : busy
      ? "正在起笔…"
      : "发起推演";
  const submitDisabled = locked ? !canSubmitStrategy || busy : !characterId || busy || characters === null;

  return (
    <section className={`panel world-story scenario-challenge is-${view === "book" ? "book" : "draft"}`}>
      <BackButton to={backHref} label="退出并返回异闻详情" />
      <header className="scenario-challenge__masthead">
        <div>
          <h1>{context.scenario.name}</h1>
          <p className="muted">{context.scenario.subtitle}</p>
          {challenge?.is_preview && <p className="muted">异闻录试炼 · 不计入统计</p>}
        </div>
        <div className="scenario-challenge__actions">
          <Link className="btn btn-ghost" to={recordsHref}>
            <BookIcon size={15} />
            翻阅往期
          </Link>
          <span className={`scenario-stream-status is-${currentId ? stage : "ready"}`}>
            {currentId ? STAGE_TEXT[stage] : "等待起笔"}
          </span>
        </div>
      </header>

      {view === "booting" ? (
        <div className="skeleton" style={{ height: 420, margin: 24 }} />
      ) : view === "book" ? (
        <div className="scenario-book">
          <aside className="scenario-rail">
            <div className="scenario-stages" aria-label="推演进度">
              {STAGE_STEPS.map((step, index) => {
                const reached = !!currentId && ORDER[stage] >= ORDER[step];
                const running = !!currentId && stage === step && stage !== "result";
                return (
                  <span
                    className={`scenario-stage${reached ? " is-done" : ""}${running ? " is-active" : ""}`}
                    key={step}
                  >
                    <i className="scenario-stage__dot" aria-hidden="true" />
                    <b className="scenario-stage__no">{String(index + 1).padStart(2, "0")}</b>
                    <span className="scenario-stage__label">{STAGE_TEXT[step]}</span>
                  </span>
                );
              })}
            </div>
            {stage === "result" && challenge && (
              <div className={`scenario-result ${challenge.won ? "is-won" : "is-lost"}`}>
                <span className="scenario-result__seal">
                  <SealStamp char={challenge.won ? "胜" : "负"} size={40} />
                </span>
                <div className="scenario-result__body">
                  <strong>
                    {challenge.won ? "本次推演：对局目标已达成" : "本次推演：对局目标未达成"}
                  </strong>
                  {challenge.derived?.reason && <p>{challenge.derived.reason}</p>}
                  {!owner && !challenge.is_preview && !challenge.god_unlocked && (
                    <p className="muted">待你看破这条异闻的全部奇术，推演全文会在书页上开启。</p>
                  )}
                  <div className="scenario-result__actions">
                    <button className="btn btn-primary" onClick={restart}>
                      <RefreshIcon size={15} />
                      换策略再推演
                    </button>
                    <Link className="btn btn-ghost" to={`${recordsHref}?run=${challenge.id}`}>
                      <BookIcon size={15} />
                      回看本局
                    </Link>
                    <Link className="btn btn-ghost" to={backHref}>
                      <XIcon size={15} />
                      返回详情
                    </Link>
                  </div>
                </div>
              </div>
            )}
            {error && <p className="err">{error}</p>}
          </aside>
          <ScenarioManuscript
            variant="book"
            messages={challenge?.messages ?? []}
            own={own}
            ownLabel={ownLabel}
            liveText={liveOwn}
            liveDeduction={liveDeduction}
            emptyText=""
            runningHead={{ left: context.scenario.name, right: preview ? "异闻录试炼" : `第 ${runNumber} 次推演` }}
            folio={{ left: "小天下集", right: preview ? "— 试 —" : `— ${chineseNumber(runNumber)} —` }}
          />
        </div>
      ) : (
        <>
          <div className="scenario-info">
            <div className="scenario-info__main">
              <div className="scenario-info__block">
                <div className="scenario-info__label">
                  <span className="eyebrow">对局目标</span>
                </div>
                <p className="scenario-info__goal">{context.scenario.victory_condition}</p>
              </div>
              <div className="scenario-opponent">
                <div className="scenario-opponent__head">
                  <span className="eyebrow">本场对手</span>
                  <strong>{context.roster.character_name}</strong>
                  <span className="chip chip--ability">{abilityTotal} 门奇术</span>
                </div>
                <p className="scenario-opponent__bio">{context.roster.character_bio || "此人未留行状。"}</p>
                <p className="scenario-opponent__stats">
                  <span>
                    已看破 {cracked} / {abilityTotal} 门
                  </span>
                  <span>{winRate}</span>
                </p>
              </div>
              <p className="scenario-info__meta">
                <span>{preview ? "异闻录试炼" : `本场已推演 ${attempts} 次`}</span>
                <span>{locked ? STAGE_TEXT[stage] : preview ? "试炼" : `第 ${nextRun} 次`}</span>
              </p>
            </div>
            <div className="scenario-info__rules">
              <section className="scenario-rules">
                <h3 className="scenario-rules__title">
                  卷规则<span className="scenario-rules__badge">最高优先级</span>
                </h3>
                <ol className="scenario-rules__list">
                  {context.scenario.rules.map((rule) => (
                    <li key={rule}>{rule}</li>
                  ))}
                </ol>
              </section>
              <section className="scenario-rules scenario-rules--dim">
                <h3 className="scenario-rules__title">
                  补充判定<span className="scenario-rules__badge">含糊即未发生</span>
                </h3>
                <ul className="scenario-rules__list">
                  {context.scenario.judgement_rules.map((rule) => (
                    <li key={rule}>{rule}</li>
                  ))}
                </ul>
              </section>
            </div>
          </div>

          <div className="scenario-divider">
            <span>其二 · 起笔</span>
          </div>

          <section className="scenario-console">
            <div className="scenario-picker">
              <div className="scenario-picker__head">
                <span className="eyebrow">出战奇人</span>
                <span className="scenario-picker__hint">
                  {characters === null ? "载入中" : `共 ${available.length} 位`}
                  {characters !== null && available.length > 4 && <span className="scenario-picker__more"> · 可滚</span>}
                </span>
              </div>
              <div className="scenario-picker__list" role="radiogroup" aria-label="出战奇人">
                {characters === null
                  ? [0, 1, 2].map((row) => <span className="scenario-picker__ghost" key={row} />)
                  : available.map((character) => (
                      <label className="scenario-picker__row" key={character.id}>
                        <input
                          type="radio"
                          name="battle-character"
                          value={character.id}
                          checked={characterId === character.id}
                          onChange={() => setCharacterId(character.id)}
                          disabled={locked || busy}
                        />
                        <span className="scenario-picker__mark" aria-hidden="true" />
                        <span className="scenario-picker__body">
                          <b>{character.name}</b>
                          <small>{character.bio || "未留行状"}</small>
                        </span>
                        <span className="scenario-picker__arts">{artsOf(character)}</span>
                      </label>
                    ))}
              </div>
              {characters !== null && !available.length ? (
                <p className="scenario-picker__empty">
                  暂无可用奇人，请先在 <Link to="/yiwenlu">异闻录</Link> 装配 1-4 门奇术。
                </p>
              ) : (
                <p className="scenario-picker__foot">
                  {locked
                    ? `本局奇人已定${ownLabel ? ` · ${ownLabel}` : ""}，只可改策略。`
                    : "选定后仍可改，起笔那一刻才算数。"}
                </p>
              )}
            </div>

            <div className="scenario-sheet">
              <div className="scenario-sheet__head">
                <span className="eyebrow">策略意图</span>
                <span className="scenario-sheet__count">
                  {strategy.length} / 1000
                </span>
              </div>
              <textarea
                id="battle-strategy"
                maxLength={1000}
                value={strategy}
                onChange={(event) => setStrategy(event.target.value)}
                placeholder="告诉奇人该如何应对这场推演；留空则由奇人自行应对。"
              />
              <div className="scenario-sheet__foot">
                <p className="muted">
                  {locked ? "比对完成后点「开始推演」，或留空让奇人自行应对。" : "留空则由奇人自行应对。"}
                </p>
                <button className="btn btn-primary" disabled={submitDisabled} onClick={() => void (locked ? derive() : begin())}>
                  {submitLabel}
                </button>
              </div>
              {error && <p className="err">{error}</p>}
            </div>
          </section>
        </>
      )}
    </section>
  );
}
