import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { streamEvents } from "../sse";
import { startScenarioChallenge } from "../scenarioChallenge";
import { SealStamp } from "../components/Ornaments";
import { BookIcon, ChevronLeftIcon, RefreshIcon, XIcon } from "../components/icons";
import { ScenarioManuscript } from "../components/ScenarioNarrative";
import { STAGE_STEPS, STAGE_TEXT, isInProgress, type Message, type ScenarioHistoryItem, type Stage } from "../scenarioModel";
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
  roster: { character_name: string; ability_count: number };
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
 * 对战页：归属阵容（擂台）的常驻地址，起笔前后的唯一对战页面。
 * 单栏书页 + 单主视角（上帝遮挡块 → 己方正文）；猜词入口本轮搁置；往期记录在独立的记录阅读页。
 */
export default function ScenarioBattle() {
  const { scenarioSlug, rosterId } = useParams<{ scenarioSlug: string; rosterId: string }>();
  const [context, setContext] = useState<RosterContext | null>(null);
  const [characters, setCharacters] = useState<Character[] | null>(null);
  const [contextToken, setContextToken] = useState(0);
  const [characterId, setCharacterId] = useState("");
  const [strategy, setStrategy] = useState("");
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [challenge, setChallenge] = useState<Challenge | null>(null);
  const [stage, setStage] = useState<Stage>("loading");
  const [liveGod, setLiveGod] = useState("");
  const [liveOwn, setLiveOwn] = useState("");
  const [streamRetry, setStreamRetry] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const ownSideRef = useRef<"challenger" | "guardian">("challenger");
  const resolved = useRef(false);
  const pendingDerive = useRef(false);
  const deriveRef = useRef<() => void>(() => {});

  // 阵容上下文（擂台）与自家奇人
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

  useEffect(() => {
    api<Character[]>("/creator/characters")
      .then(setCharacters)
      .catch(() => setCharacters([]));
  }, []);

  // 首屏若这座擂台上有未终局的回合，直接续上；没有就等新局
  useEffect(() => {
    if (!context || resolved.current) return;
    resolved.current = true;
    const live = context.my_challenges.find((item) => isInProgress(item.status));
    if (live) {
      setCharacterId(live.challenger_character_id ?? "");
      setCurrentId(live.id);
    }
  }, [context]);

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
        ownSideRef.current = data.viewer_role === "owner" ? "guardian" : "challenger";
        const next: Stage = stageFromStatus(data.status);
        setStage((current) => (ORDER[next] >= ORDER[current] || current === "loading" ? next : current));
        const prior = data.messages.find((message) => message.role === "challenger");
        if (prior) setStrategy(prior.text ?? "");
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
          if (event.type === "god_progress") {
            // 上帝遮挡流：只收到累计字数，前端按字数合成遮挡符号（真实文本不出站）
            // 密度 1 符 / 20 字、上限 240 符——稳定增长且不撑爆版面
            const chars = Number(event.chars ?? 0);
            setLiveGod("❖".repeat(Math.min(240, Math.max(1, Math.ceil(chars / 20)))));
            setStage((current) => (ORDER["thinking"] >= ORDER[current] ? "thinking" : current));
          } else if (event.type === "view_chunk") {
            // 服务端已按侧别过滤：本连接只会收到己方转写
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
            setLiveGod("");
            setLiveOwn("");
          } else if (event.type === "error") {
            setError(String(event.message ?? "衍算未能完成"));
            setStage("compare");
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
  // 本次是从战斗台发起的：比对完成的那一刻自动提交策略，免二次点击
  useEffect(() => {
    if (!pendingDerive.current || !canSubmitStrategy) return;
    pendingDerive.current = false;
    deriveRef.current();
  }, [canSubmitStrategy]);

  // 仅装配 1-4 门奇术的自家奇人可出战（与后端 _character_snapshot 的约束一致）
  const available = useMemo(
    () => (characters ?? []).filter((c) => c.ability_ids.length >= 1 && c.ability_ids.length <= 4),
    [characters],
  );

  if (!context)
    return error ? <p className="err">{error}</p> : <div className="skeleton" style={{ height: 320 }} />;

  const failed = challenge?.status === "failed";
  const hasRun = !!challenge && !failed;
  const owner = challenge?.viewer_role === "owner";
  const own: "challenger" | "guardian" = owner ? "guardian" : "challenger";
  const ownLabel = owner ? challenge?.roster.character_name ?? "" : challenge?.challenger.character_name ?? "";
  const backHref = `/scenarios/${scenarioSlug}/rosters/${rosterId}`;
  const recordsHref = `${backHref}/records`;

  const begin = async () => {
    if (!rosterId || !characterId || busy) return;
    setBusy(true);
    setError("");
    try {
      const id = await startScenarioChallenge(rosterId, characterId);
      pendingDerive.current = true;
      setLiveGod("");
      setLiveOwn("");
      setCurrentId(id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "起笔失败");
    } finally {
      setBusy(false);
    }
  };

  const derive = async () => {
    if (!currentId || !canSubmitStrategy) return;
    setError("");
    setStage("thinking");
    setChallenge((current) => (current ? { ...current, status: "resolving" } : current));
    try {
      await api(`/scenario-challenges/${currentId}/derive`, {
        method: "POST",
        body: JSON.stringify({ strategy: strategy.trim() }),
      });
    } catch (cause) {
      setStage("ready");
      setChallenge((current) => (current ? { ...current, status: "active" } : current));
      setError(cause instanceof Error ? cause.message : "推演启动失败");
    }
  };

  // 再战：清空当前回合但不离开擂台，沿用本场的奇人与策略
  const restart = () => {
    if (challenge) setCharacterId(challenge.challenger.character_id ?? characterId);
    pendingDerive.current = false;
    setLiveGod("");
    setLiveOwn("");
    setCurrentId(null);
  };

  deriveRef.current = derive;

  const strategyField = (
    <label htmlFor="battle-strategy">
      挑战者策略意图 <small className="muted">{strategy.length}/1000</small>
    </label>
  );

  return (
    <section className="panel world-story scenario-challenge">
      <Link className="scenario-back" to={backHref} aria-label="退出并返回阵容详情">
        <ChevronLeftIcon size={20} />
      </Link>
      <header className="scenario-challenge__masthead">
        <div>
          <h1>{context.scenario.name}</h1>
          <p className="muted">{context.scenario.subtitle}</p>
          {challenge?.is_preview && <p className="muted">创作台试炼 · 不计入统计</p>}
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
      <div className="scenario-stagebar" aria-label="推演进度">
        {STAGE_STEPS.map((step, index) => (
          <span className={currentId && ORDER[stage] >= ORDER[step] ? "is-done" : ""} key={step}>
            <i>{index + 1}</i>
            {STAGE_TEXT[step]}
          </span>
        ))}
      </div>
      <div className="world-story__brief scenario-brief">
        <p className="scenario-brief__goal">
          <strong>挑战目标：</strong>
          {context.scenario.victory_condition}
        </p>
        <details className="scenario-fold">
          <summary>卷规则 · 最高优先级</summary>
          <ul>{context.scenario.rules.map((rule) => <li key={rule}>{rule}</li>)}</ul>
        </details>
        <details className="scenario-fold">
          <summary>补充判定规则</summary>
          <ul>{context.scenario.judgement_rules.map((rule) => <li key={rule}>{rule}</li>)}</ul>
        </details>
        {challenge?.derived?.comparison_report && (
          <details className="scenario-fold">
            <summary>查看奇术比对报告</summary>
            <p className="scenario-fold__prose">{challenge.derived.comparison_report}</p>
          </details>
        )}
      </div>
      <div className="scenario-challenge__layout is-solo">
        <ScenarioManuscript
          messages={challenge?.messages ?? []}
          own={own}
          ownLabel={ownLabel}
          title={challenge ? `第 ${challenge.challenge_number} 次推演` : "行迹"}
          liveText={liveOwn}
          liveGod={liveGod}
          note={!currentId ? "等待起笔" : challenge?.won === null ? "实时落墨" : "本场结局已记录"}
          emptyText={
            hasRun
              ? "奇术比对完成后，整场推演将一次成卷。"
              : "选定奇人、写下策略，发起推演，行迹将在此逐字落墨。"
          }
          pending={stage === "thinking" || stage === "views"}
        >
          {!currentId || failed ? (
            <div className="scenario-guidance">
              <label htmlFor="battle-character">出战奇人</label>
              <select
                id="battle-character"
                value={characterId}
                onChange={(event) => setCharacterId(event.target.value)}
                disabled={busy || characters === null}
              >
                <option value="">请选择奇人</option>
                {available.map((character) => (
                  <option key={character.id} value={character.id}>
                    {character.name}
                  </option>
                ))}
              </select>
              {characters !== null && !available.length && (
                <p className="muted">
                  暂无可用奇人，请先在 <Link to="/creator">创作台</Link> 装配 1-4 门奇术。
                </p>
              )}
              {strategyField}
              <textarea
                id="battle-strategy"
                rows={5}
                maxLength={1000}
                value={strategy}
                onChange={(event) => setStrategy(event.target.value)}
                placeholder="告诉奇人该如何应对这场推演；留空则由奇人自行应对。"
              />
              <button
                className="btn btn-primary"
                disabled={!characterId || busy}
                onClick={() => void begin()}
              >
                {busy ? "正在起笔…" : "发起推演"}
              </button>
            </div>
          ) : (
            challenge &&
            challenge.won === null &&
            stage !== "result" && (
              <div className="scenario-guidance">
                {strategyField}
                <textarea
                  id="battle-strategy"
                  value={strategy}
                  onChange={(event) => setStrategy(event.target.value)}
                  placeholder="写下希望奇人优先采取的策略，也可以留空跳过"
                  disabled={!canSubmitStrategy && stage !== "compare"}
                />
                <button
                  className="btn btn-primary"
                  disabled={!canSubmitStrategy}
                  onClick={() => void derive()}
                >
                  {strategy.trim() ? "开始推演" : "跳过指导并推演"}
                </button>
              </div>
            )
          )}
        </ScenarioManuscript>
      </div>
      {error && <p className="err">{error}</p>}
      {stage === "result" && challenge && (
        <div className={`scenario-result ${challenge.won ? "is-won" : "is-lost"}`}>
          <span className="scenario-result__seal">
            <SealStamp char={challenge.won ? "胜" : "负"} size={48} />
          </span>
          <div className="scenario-result__body">
            <strong>
              {challenge.won ? "本次推演：挑战目标已达成" : "本次推演：挑战目标未达成"}
            </strong>
            {challenge.derived?.reason && <p>{challenge.derived.reason}</p>}
            {!owner && !challenge.is_preview && !challenge.god_unlocked && (
              <p className="muted">待你看破这套阵容的全部奇术，上帝视角会在书页上开启。</p>
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
    </section>
  );
}