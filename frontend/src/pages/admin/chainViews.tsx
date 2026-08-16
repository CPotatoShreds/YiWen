// 行迹展示共享组件：StoryView（讨论/上帝/甲/乙 页签）与 TracePanel（LLM 调用链）。
// 试验台（TestArena，test_* 数据）与行迹链路还原（BattleChain，真实行迹）共用。

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../../api";
import Markdown from "../../components/Markdown";
import { CheckIcon, LockIcon } from "../../components/icons";
import type { AdminBattle, LlmTrace, LlmTraceDetail } from "./types";
import {
  CAT_GUESS_PAIR,
  CAT_LABEL,
  buildSummary,
  categorize,
  fmtDt,
  fmtMs,
  statusLabel,
} from "./traceParsers";
import { PairGrid, TraceView } from "./TraceViews";

const emptyStory = "（无叙述，指定胜负跳过）";

/** 宽松故事结构：真实行迹 story 是 Record<string,unknown>，试验场 TestBattleStory 字段皆为 string。 */
export interface StoryLike {
  narration?: unknown;
  narration_a?: unknown;
  narration_b?: unknown;
  discuss_report?: unknown;
}

const str = (v: unknown): string => (typeof v === "string" ? v : "");

/**
 * 三视角页签展示。真实行迹的讨论报告不在 story 里，由调用方从 discuss trace 提取后经
 * discussReport 传入（覆盖 story.discuss_report）；试验台直接用 story.discuss_report。
 * 传 guess 时追加「拆字」页签，与 讨论/三视角 并列切换。
 */
export function StoryView({
  story,
  discussReport,
  guess,
  defaultTab = "god",
}: {
  story: StoryLike | null;
  discussReport?: string;
  guess?: ReactNode;
  defaultTab?: "discuss" | "god" | "a" | "b" | "guess";
}) {
  const [tab, setTab] = useState<"discuss" | "god" | "a" | "b" | "guess">(defaultTab);
  const content =
    tab === "discuss"
      ? discussReport ?? str(story?.discuss_report)
      : tab === "god"
        ? str(story?.narration)
        : tab === "a"
          ? str(story?.narration_a)
          : str(story?.narration_b);
  const showGuess = tab === "guess" && guess != null;
  return (
    <div className="story-view">
      <div className="admin-tabs">
        <button className={tab === "discuss" ? "is-active" : ""} onClick={() => setTab("discuss")}>讨论</button>
        <button className={tab === "god" ? "is-active" : ""} onClick={() => setTab("god")}>上帝视角</button>
        <button className={tab === "a" ? "is-active" : ""} onClick={() => setTab("a")}>甲 视角</button>
        <button className={tab === "b" ? "is-active" : ""} onClick={() => setTab("b")}>乙 视角</button>
        {guess != null && (
          <button className={tab === "guess" ? "is-active" : ""} onClick={() => setTab("guess")}>拆字</button>
        )}
      </div>
      {showGuess ? (
        guess
      ) : content ? (
        <Markdown className="story-view__text" text={content} />
      ) : (
        <p className="muted">{emptyStory}</p>
      )}
    </div>
  );
}

/**
 * LLM 调用链面板：按环节分组展示某场行迹的全部 trace（含请求/响应详情，懒加载）。
 * kinds 决定取哪些链路（试验台 test_battle/test_guess，真实行迹 battle/guess）。
 */
export function TracePanel({
  battleId,
  kinds = ["test_battle", "test_guess"],
  limit,
}: {
  battleId: number;
  kinds?: string[];
  limit?: number;
}) {
  const [traces, setTraces] = useState<LlmTrace[]>([]);
  const [details, setDetails] = useState<Record<number, LlmTraceDetail>>({});
  const [open, setOpen] = useState<number | null>(null);
  const [err, setErr] = useState("");

  // kinds 为默认参数时每渲染重建数组，用 join 字符串做稳定依赖，避免无限重拉
  const kindKey = kinds.join(",");
  const limitQuery = limit ? `&limit=${limit}` : "";

  const load = () => {
    Promise.all(
      kinds.map((k) => api<LlmTrace[]>(`/admin/llm-traces?trace_id=${battleId}&kind=${k}${limitQuery}`))
    )
      .then((lists) => {
        const merged = lists.flat().sort((x, y) => x.id - y.id);
        setTraces(merged);
        setDetails({});
        setOpen(null);
      })
      .catch((e: Error) => setErr(e.message));
  };

  useEffect(load, [battleId, kindKey, limitQuery]);

  async function toggleDetail(t: LlmTrace) {
    if (open === t.id) {
      setOpen(null);
      return;
    }
    setErr("");
    try {
      if (!details[t.id]) {
        const data = await api<LlmTraceDetail>(`/admin/llm-traces/${t.id}`);
        setDetails((prev) => ({ ...prev, [t.id]: data }));
      }
      setOpen(t.id);
    } catch (e: any) {
      setErr(e.message);
    }
  }

  // 环节顺序：讨论 → 推演 → 转写 → 校验/修复 → usage → 猜词三环节
  const ORDER = [
    "discuss",
    "deduce",
    "transcribe",
    "validate",
    "repair",
    "usage",
    "guess_split",
    "guess_pair",
    "guess_verify",
  ];
  const groups = useMemo(() => {
    const m = new Map<string, LlmTrace[]>();
    for (const t of traces) {
      const k = categorize(t.operation);
      m.set(k, [...(m.get(k) ?? []), t]);
    }
    return [...m.entries()].sort(
      (a, b) => ORDER.indexOf(a[0]) - ORDER.indexOf(b[0])
    );
  }, [traces]);

  // 汇总头部：usage 判定 + 环节覆盖
  const summary = useMemo(() => buildSummary(traces, details), [traces, details]);
  const covered = groups
    .filter(([k]) => ORDER.includes(k))
    .map(([k]) => k);

  return (
    <div className="trace-panel">
      <div className="trace-panel__bar">
        <span className="muted">共 {traces.length} 条调用</span>
        <button className="btn btn-ghost btn-sm" onClick={load}>刷新</button>
      </div>
      {err && <p className="err">{err}</p>}
      {traces.length === 0 && !err && <p className="muted">本次对局暂无 LLM 调用记录。</p>}
      {traces.length > 0 && (
        <div className="trace-panel__meta">
          <span className="trace-panel__meta-item">
            环节 <b>{covered.length}/{ORDER.length}</b>
          </span>
          <span className="trace-panel__meta-item">
            失败 <b className={traces.some((t) => t.status === "fail") ? "is-bad" : ""}>{traces.filter((t) => t.status === "fail").length}</b>
          </span>
          {summary.usedAbilityIdx.length > 0 && (
            <span className="trace-panel__meta-item">
              实际使用 <b className="is-used">{summary.usedAbilityIdx.join("、")}</b>
            </span>
          )}
          {summary.usageFailed && <span className="trace-panel__meta-item is-bad">使用判定失败</span>}
        </div>
      )}
      {groups.map(([cat, rows]) => {
        const isPair = cat === CAT_GUESS_PAIR;
        return (
          <div key={cat} className="trace-group">
            <div className="trace-group__head">
              <b>{CAT_LABEL[cat] ?? cat}</b>
              <span className="muted">{rows.length} 次</span>
            </div>
            {isPair && rows.length > 1 && (
              <PairGrid details={rows.map((r) => details[r.id]).filter(Boolean) as LlmTraceDetail[]} />
            )}
            {rows.map((t) => (
              <div className={`trace-row ${open === t.id ? "is-open" : ""}`} key={t.id}>
                <button className="trace-row__main" onClick={() => toggleDetail(t)}>
                  <span className={`trace-dot trace-dot--${t.status}`} />
                  <span className="trace-row__status">
                    {t.status === "ok" ? "成功" : t.status === "fail" ? "失败" : t.status}
                  </span>
                  <span className="trace-row__ms mono">{fmtMs(t.latency_ms)}</span>
                  <span className="trace-row__tokens mono">{t.tokens_input}→{t.tokens_output}</span>
                  <span className="trace-row__time mono">{fmtDt(t.created_at)}</span>
                  <span className="trace-row__op">#{t.id}</span>
                </button>
                {open === t.id && (
                  <div className="trace-row__detail">
                    {t.error && <p className="err">{t.error}</p>}
                    {details[t.id] ? (
                      <TraceView d={details[t.id]} />
                    ) : (
                      <p className="muted">加载中…</p>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
}

/**
 * 拆字内容（StoryView「拆字」页签）：猜测者逐次道出的猜测原文流 + 奇术卡片网格
 * （未看破显线索片段，看破揭示真名）。复用用户端 GuessBoard/GuessFeed 的样式类。
 */
export function GuessPanel({ battle }: { battle: AdminBattle }) {
  const cards = battle.guess_cards ?? [];
  if (battle.guess_cards === null && battle.guess_history.length === 0) return null;
  const cracked = cards.filter((c) => c.cracked).length;
  const hitLabel = battle.guess_hit === null ? "未结算" : battle.guess_hit ? "命中" : "未命中";
  return (
    <div className="guess-tab">
      <p className="guess-tab__meta">
        <b>{battle.guess_by ?? "未知"}</b> 猜 · {battle.guess_attempts_used}/{battle.guess_attempts_max} 次
        {" · "}看破 {cracked}/{cards.length} 门
        {" · "}<b style={battle.guess_hit ? { color: "var(--success)" } : undefined}>{hitLabel}</b>
      </p>
      {battle.guess_history.length > 0 && (
        <ul className="guess-feed">
          {battle.guess_history.map((t, i) => (
            <li key={i}>{t}</li>
          ))}
        </ul>
      )}
      <div className="guess-board">
        {cards.map((card) => (
          <div key={card.index} className={`guess-card ${card.cracked ? "guess-card--cracked" : ""}`}>
            <div className="guess-card__head">
              <span className="guess-card__no">第 {card.index} 门</span>
              {card.cracked ? (
                <span className="guess-card__label guess-card__label--hit">
                  <CheckIcon size={13} /> 已看破{card.cracked_round ? ` · 第 ${card.cracked_round} 轮` : ""}
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
              card.matched.length > 0 && (
                <ul className="guess-card__matched">
                  {card.matched.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              )
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * 单场真实行迹的完整链路展示：拉取行迹 + 战前讨论报告（discuss trace），
 * 渲染 讨论/三视角 页签与 LLM 调用链。链路页（BattleChain）与奇人库（LoadoutBrowser）共用。
 */
export function BattleChainView({ id }: { id: number }) {
  const [battle, setBattle] = useState<AdminBattle | null>(null);
  const [discussReport, setDiscussReport] = useState("");
  const [discussNote, setDiscussNote] = useState("");
  const [err, setErr] = useState("");

  const load = () => {
    setErr("");
    setDiscussReport("");
    setDiscussNote("");
    Promise.all([
      api<AdminBattle>(`/admin/battles/${id}`),
      api<LlmTrace[]>(`/admin/llm-traces?trace_id=${id}&kind=battle&operation=discuss&limit=3`),
    ])
      .then(async ([b, discussRows]) => {
        setBattle(b);
        const okTrace = discussRows.find((t) => t.status === "ok");
        if (okTrace) {
          const d = await api<LlmTraceDetail>(`/admin/llm-traces/${okTrace.id}`);
          if (typeof d.response_json === "string") {
            setDiscussReport(d.response_json);
          } else {
            setDiscussNote("讨论调用返回非文本输出");
          }
        } else if (discussRows.length === 0) {
          setDiscussNote("本场无讨论调用记录（可能未走讨论链路）");
        } else {
          setDiscussNote("本场讨论调用失败，无成功报告");
        }
      })
      .catch((e: Error) => {
        setErr(e.message);
        setBattle(null);
      });
  };

  useEffect(load, [id]);

  if (err) return <p className="err">{err}</p>;
  if (!battle) return <p className="muted">加载中…</p>;

  return (
    <div className="panel">
      <div className="panel__head">
        <h3>行迹 #{battle.id}</h3>
        <span className="muted">
          <b>{battle.user_a ?? "已离席"}</b> 对 <b>{battle.user_b ?? "已离席"}</b>
          {" · "}<span className={`status-chip status-chip--${battle.status}`}>{statusLabel(battle.status)}</span>
          {battle.winner ? ` · 胜者：${battle.winner}` : ""}
        </span>
      </div>
      {battle.status === "failed" && (
        <p className="err">推演失手：{String((battle.story as Record<string, unknown> | null)?.error_message ?? "未知原因")}</p>
      )}
      {battle.status === "pending" && <p className="muted">推演进行中，链路可能不全。</p>}
      <StoryView
        story={battle.story ?? null}
        discussReport={discussReport}
        guess={battle.guess_cards !== null || battle.guess_history.length > 0 ? <GuessPanel battle={battle} /> : undefined}
        defaultTab="discuss"
      />
      {discussNote && <p className="muted">{discussNote}</p>}
      <TracePanel battleId={battle.id} kinds={["battle", "guess"]} limit={500} />
    </div>
  );
}
