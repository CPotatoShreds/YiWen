import { useEffect, useMemo, useState } from "react";
import { api } from "../../api";
import {
  CheckIcon,
  EyeIcon,
  LockIcon,
  PlusIcon,
  TrashIcon,
  XIcon,
} from "../../components/icons";
import type {
  Ability,
  LlmTrace,
  LlmTraceDetail,
  TestBattle,
  TestBattleStory,
  TestGuessCard,
  TestLoadout,
  TestUser,
} from "./types";
import { CAT_GUESS_PAIR, CAT_LABEL, buildSummary, categorize } from "./traceParsers";
import { PairGrid, TraceView } from "./TraceViews";

const statusLabel = (s: string) => (s === "pending" ? "推演中" : s === "failed" ? "失手" : "已落成");

const fmtMs = (ms: number) => (ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`);
const fmtDt = (iso: string) => iso.replace("T", " ").slice(0, 19);

function GuessBoard({ cards }: { cards: TestGuessCard[] }) {
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
  );
}

const emptyStory = "（无叙述，指定胜负跳过）";

/**
 * 猜词累计描述表：每轮猜测一张表。行 = 本轮拆出的原子叙述，列 = 对家奇术。
 * 格子 = 该奇术累计解锁的描述：本轮新增红色、历史黑色；看破的列带标记；
 * 有本轮增量的格子可点击，切换显示该轮「看破 / 未看破」的检定原因。
 */
/**
 * 猜词累计描述表：每轮猜测一张表，且**冻结在该轮**——只显示截止到该轮的累计描述，
 * 后续轮次新增不回写。行 = 该轮拆出的原子叙述，列 = 对家奇术。
 * 原子叙述命中了哪列，就在那列写该奇术累计解锁的描述（本轮新增红色、历史黑色）；
 * 未命中的格子留空。看破的列带标记；有本轮增量的格子可点击切换检定原因。
 */
function GuessMatrix({ cards }: { cards: TestGuessCard[] }) {
  const [openCell, setOpenCell] = useState<{ ci: number; round: number } | null>(null);
  // 每张卡按轮索引（rounds 已按轮序落库，每轮都有）
  const cardRoundsOf = (c: TestGuessCard) => c.rounds ?? [];
  const rounds = Math.max(0, ...cards.map((c) => cardRoundsOf(c).length));
  if (rounds === 0) {
    return <p className="muted">尚无猜词回合，提交猜测后这里会出现「原子叙述 × 奇术」的累计描述表。</p>;
  }
  // 本轮原子叙述 = 任一卡该轮记录（各卡该轮 items 相同）
  const itemsOf = (r: number): string[] => {
    for (const c of cards) {
      const rnd = cardRoundsOf(c)[r - 1];
      if (rnd) return rnd.items ?? [];
    }
    return [];
  };
  return (
    <div className="guess-matrices">
      {Array.from({ length: rounds }, (_, i) => i + 1).map((r) => {
        const items = itemsOf(r);
        return (
          <div className="guess-matrix" key={r}>
            <div className="guess-matrix__head">
              <b>第 {r} 次猜测</b>
              <span className="muted">{items.length > 0 ? `${items.length} 条原子叙述` : "（本轮未拆出条目）"}</span>
            </div>
            <div className="table-wrap">
              <table className="guess-matrix__table">
                <thead>
                  <tr>
                    <th className="guess-matrix__corner">原子叙述 \ 奇术</th>
                    {cards.map((c) => (
                      <th key={c.index}>
                        <span>第 {c.index} 门</span>
                        {c.cracked && c.cracked_round != null && c.cracked_round <= r && (
                          <span className="guess-matrix__crack">看破</span>
                        )}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {items.map((atom, ai) => (
                    <tr key={ai}>
                      <th scope="row" className="guess-matrix__atom">{atom}</th>
                      {cards.map((c) => {
                        const cRounds = cardRoundsOf(c);
                        const thisRoundPairs = cRounds[r - 1]?.pairs ?? [];
                        // 本行原子叙述是否命中该奇术（本轮给它带来**有价值**的新增条目）；未命中则格子留空
                        const hitThisRound = thisRoundPairs.some((p) => p.item === atom && p.snippet);
                        // 截止到本轮累计：从第 1 轮到第 r 轮所有命中的片段
                        const thru = cRounds.slice(0, r).flatMap((x) => x.pairs.filter((p) => p.snippet).map((p) => p.snippet));
                        // 本轮新增
                        const newSnippets = new Set(thisRoundPairs.filter((p) => p.snippet).map((p) => p.snippet));
                        if (thru.length === 0 || !hitThisRound) return <td key={c.index} className="guess-matrix__cell guess-matrix__cell--empty" />;
                        const hasNew = newSnippets.size > 0;
                        const verify = c.verifies?.find((v) => v.round === r);
                        const crackedHere = c.cracked && c.cracked_round != null && c.cracked_round <= r;
                        const isOpen = openCell?.ci === c.index && openCell?.round === r;
                        return (
                          <td key={c.index} className={`guess-matrix__cell ${crackedHere ? "guess-matrix__cell--cracked" : ""}`}>
                            <button
                              type="button"
                              className="guess-matrix__desc"
                              disabled={!hasNew}
                              title={hasNew ? "点击查看看破 / 未看破判定" : undefined}
                              onClick={() => setOpenCell(isOpen ? null : { ci: c.index, round: r })}
                            >
                              {crackedHere && <span className="guess-matrix__crack-inline">看破</span>}
                              {thru.map((s, i) => (
                                <span key={i} className={newSnippets.has(s) ? "is-new" : "is-old"}>{s}</span>
                              ))}
                            </button>
                            {isOpen && verify && (
                              <div className={`guess-matrix__reason ${verify.guessed ? "is-hit" : ""}`}>
                                <b>{verify.guessed ? "看破" : "未看破"}</b>：{verify.reason}
                              </div>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function StoryView({ story }: { story: TestBattleStory }) {
  const [tab, setTab] = useState<"discuss" | "god" | "a" | "b">("god");
  const content =
    tab === "discuss"
      ? story.discuss_report
      : tab === "god"
        ? story.narration
        : tab === "a"
          ? story.narration_a
          : story.narration_b;
  return (
    <div className="story-view">
      <div className="admin-tabs">
        <button className={tab === "discuss" ? "is-active" : ""} onClick={() => setTab("discuss")}>讨论</button>
        <button className={tab === "god" ? "is-active" : ""} onClick={() => setTab("god")}>上帝视角</button>
        <button className={tab === "a" ? "is-active" : ""} onClick={() => setTab("a")}>甲 视角</button>
        <button className={tab === "b" ? "is-active" : ""} onClick={() => setTab("b")}>乙 视角</button>
      </div>
      {content ? (
        <p className="story-view__text" style={{ whiteSpace: "pre-wrap" }}>{content}</p>
      ) : (
        <p className="muted">{emptyStory}</p>
      )}
    </div>
  );
}

function TracePanel({ battleId }: { battleId: number }) {
  const [traces, setTraces] = useState<LlmTrace[]>([]);
  const [details, setDetails] = useState<Record<number, LlmTraceDetail>>({});
  const [open, setOpen] = useState<number | null>(null);
  const [err, setErr] = useState("");

  const load = () => {
    Promise.all([
      api<LlmTrace[]>(`/admin/llm-traces?trace_id=${battleId}&kind=test_battle`),
      api<LlmTrace[]>(`/admin/llm-traces?trace_id=${battleId}&kind=test_guess`),
    ])
      .then(([a, b]) => {
        const merged = [...a, ...b].sort((x, y) => x.id - y.id);
        setTraces(merged);
        setDetails({});
        setOpen(null);
      })
      .catch((e: Error) => setErr(e.message));
  };

  useEffect(load, [battleId]);

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

  // 环节顺序：推演 → 转写 → 校验/修复 → usage → 猜词三环节
  const ORDER = [
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

export default function TestArena() {
  const [users, setUsers] = useState<TestUser[]>([]);
  const [abilities, setAbilities] = useState<Ability[]>([]);
  const [testLoadouts, setTestLoadouts] = useState<TestLoadout[]>([]);
  const [battles, setBattles] = useState<TestBattle[]>([]);
  const [selected, setSelected] = useState<TestBattle | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  // 生成奇人：只勾奇术，名字/账号后端自动
  const [picked, setPicked] = useState<string[]>([]);

  // 对决表单
  const [aSel, setASel] = useState<number | null>(null);
  const [bSel, setBSel] = useState<number | null>(null);
  const [skipWinner, setSkipWinner] = useState<"A" | "B" | "draw">("A");
  // 仅生成报告：复用当前双方选择，只跑讨论节点（不推演、不落库）
  const [report, setReport] = useState<string | null>(null);

  // 猜词
  const [guessText, setGuessText] = useState("");
  // 详情弹窗板块：对决 / 猜词
  const [detailTab, setDetailTab] = useState<"battle" | "guess">("battle");

  const load = () =>
    Promise.all([
      api<TestUser[]>("/admin/test/users").then(setUsers),
      api<Ability[]>("/admin/abilities").then(setAbilities),
      api<TestLoadout[]>("/admin/test/loadouts").then(setTestLoadouts),
      api<TestBattle[]>("/admin/test/battles").then(setBattles),
    ]).catch((e: Error) => setErr(e.message));
  useEffect(() => {
    load();
  }, []);

  const fighters = useMemo(
    () =>
      testLoadouts.map((l) => ({
        id: l.id,
        label: `${l.username ?? "异闻师"} · ${l.name}`,
      })),
    [testLoadouts]
  );

  // 推演是后台任务：modal 打开且 pending 时轮询详情，落成后自动展示叙述并同步列表
  const selectedId = selected?.id;
  const selectedStatus = selected?.status;
  useEffect(() => {
    if (selectedStatus !== "pending" || selectedId == null) return;
    let alive = true;
    const timer = setInterval(async () => {
      try {
        const r = await api<TestBattle>(`/admin/test/battles/${selectedId}`);
        if (!alive) return;
        setSelected(r);
        if (r.status !== "pending") {
          setBattles((prev) => prev.map((b) => (b.id === r.id ? r : b)));
        }
      } catch {
        // 单次轮询失败静默，下轮重试
      }
    }, 2000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [selectedId, selectedStatus]);

  const asFighter = (id: number | null) => {
    if (id == null) return null;
    return { test_loadout_id: id };
  };

  async function generateLoadout() {
    if (picked.length === 0) return;
    setBusy(true);
    setErr("");
    try {
      await api<TestLoadout>("/admin/test/loadouts", {
        method: "POST",
        body: JSON.stringify({ abilities: picked }),
      });
      setPicked([]);
      await load();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function removeLoadout(l: TestLoadout) {
    if (!window.confirm(`确认删除奇人「${l.name}」？无对局引用时其绑定测试账号一并删除。`)) return;
    try {
      await api(`/admin/test/loadouts/${l.id}`, { method: "DELETE" });
      await load();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function runSkip() {
    setBusy(true);
    setErr("");
    try {
      const fa = asFighter(aSel);
      const fb = asFighter(bSel);
      if (!fa || !fb) throw new Error("请先为双方选择奇人");
      const r = await api<TestBattle>("/admin/test/battles/skip", {
        method: "POST",
        body: JSON.stringify({ fighter_a: fa, fighter_b: fb, winner: skipWinner }),
      });
      setSelected(r);
      await load();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function runDeduction() {
    setBusy(true);
    setErr("");
    try {
      const fa = asFighter(aSel);
      const fb = asFighter(bSel);
      if (!fa || !fb) throw new Error("请先为双方选择奇人");
      const r = await api<TestBattle>("/admin/test/battles", {
        method: "POST",
        body: JSON.stringify({ fighter_a: fa, fighter_b: fb }),
      });
      setSelected(r);
      await load();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function runReport() {
    setBusy(true);
    setErr("");
    setReport(null);
    try {
      const fa = asFighter(aSel);
      const fb = asFighter(bSel);
      if (!fa || !fb) throw new Error("请先为双方选择奇人");
      const r = await api<{ report: string }>("/admin/test/battles/report", {
        method: "POST",
        body: JSON.stringify({ fighter_a: fa, fighter_b: fb }),
      });
      setReport(r.report);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function refreshDetail(id: number) {
    const r = await api<TestBattle>(`/admin/test/battles/${id}`);
    setSelected(r);
    await load();
  }

  // 打开/刷新详情时重置弹窗板块与表格展开态
  function openDetail(b: TestBattle, tab: "battle" | "guess") {
    setDetailTab(tab);
    setSelected(b);
  }

  async function submitGuess() {
    if (!selected) return;
    setBusy(true);
    setErr("");
    try {
      await api(`/admin/test/battles/${selected.id}/guess`, {
        method: "POST",
        body: JSON.stringify({ text: guessText }),
      });
      setGuessText("");
      await refreshDetail(selected.id);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function newUser() {
    setBusy(true);
    setErr("");
    try {
      await api<TestUser>("/admin/test/users", { method: "POST", body: JSON.stringify({}) });
      await load();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function removeUser(u: TestUser) {
    if (!window.confirm(`确认删除测试账号「${u.username}」？其参与的测试行迹一并清理。`)) return;
    try {
      await api(`/admin/test/users/${u.id}`, { method: "DELETE" });
      await load();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  async function removeBattle(b: TestBattle) {
    if (!window.confirm(`确认删除测试行迹 #${b.id}？`)) return;
    try {
      await api(`/admin/test/battles/${b.id}`, { method: "DELETE" });
      await load();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  const crackedCount = (b: TestBattle) => b.guess_cards?.filter((c) => c.cracked).length ?? 0;

  return (
    <div className="admin-page">
      <div className="admin-toolbar">
        <div>
          <span className="eyebrow">BATTLE TEST GROUND</span>
          <h2>对战试验场</h2>
        </div>
        <p className="muted">纯测试模块：只写 test_* 表，对玩家数据零影响</p>
      </div>
      {err && <p className="err">{err}</p>}

      {/* 测试账号 */}
      <section className="panel">
        <div className="panel__head">
          <h3>测试账号</h3>
          <span className="muted">生成奇人自动绑定；也可手动新建</span>
          <button className="btn btn-ghost btn-sm" onClick={newUser} disabled={busy}>
            <PlusIcon size={14} /> 新建（词库起名）
          </button>
        </div>
        <div className="tbl-list">
          {users.map((u) => (
            <div className="tbl-row" key={u.id}>
              <span className="tbl-col mono">#{u.id}</span>
              <span className="tbl-col tbl-col--main"><b>{u.username}</b></span>
              <span className="tbl-col mono">{u.rank_points} 名望</span>
              <span className="tbl-col tbl-actions">
                <button className="btn btn-danger btn-icon btn-sm" onClick={() => removeUser(u)} title="删除"><TrashIcon size={14} /></button>
              </span>
            </div>
          ))}
        </div>
        {users.length === 0 && <p className="muted">尚无测试账号，生成奇人时自动创建。</p>}
      </section>

      {/* 奇人组装 */}
      <section className="panel">
        <div className="panel__head">
          <h3>奇人组装</h3>
          <span className="muted">勾选奇术 → 生成奇人：名字随机、风格空，自动绑定新测试账号并永久保存</span>
        </div>
        <div className="ability-list">
          {abilities.map((a) => (
            <label className="ability-item" key={a.id} style={{ cursor: "pointer", alignItems: "center" }}>
              <input type="checkbox" checked={picked.includes(a.id)} onChange={() => setPicked((p) => (p.includes(a.id) ? p.filter((x) => x !== a.id) : [...p, a.id]))} />
              <div className="ability-item__body">
                <div className="ability-item__name">{a.name}</div>
                <p className="ability-item__effect">{a.effect}</p>
              </div>
            </label>
          ))}
        </div>
        <button className="btn btn-primary" disabled={busy || picked.length === 0} onClick={generateLoadout}>
          <PlusIcon size={15} /> 生成奇人 {picked.length > 0 ? `（已选 ${picked.length} 门奇术）` : ""}
        </button>
        <div className="tbl-list" style={{ marginTop: 14 }}>
          {testLoadouts.map((l) => (
            <div className="tbl-row" key={l.id}>
              <span className="tbl-col mono">#{l.id}</span>
              <span className="tbl-col tbl-col--main">
                <b>{l.name}</b>
                <small>{l.abilities.map((a) => a.name).join(" · ") || "（无奇术）"}</small>
              </span>
              <span className="tbl-col muted">{l.username ?? "绑定账号"}</span>
              <span className="tbl-col tbl-actions">
                <button className="btn btn-danger btn-icon btn-sm" onClick={() => removeLoadout(l)} title="删除"><TrashIcon size={14} /></button>
              </span>
            </div>
          ))}
        </div>
        {testLoadouts.length === 0 && <p className="muted">尚无持久奇人，勾选奇术后点「生成奇人」。</p>}
      </section>

      {/* 对决 */}
      <section className="panel">
        <div className="panel__head">
          <h3>对决</h3>
          <span className="muted">真实推演走 LLM；指定胜负零 LLM 直接进猜词</span>
        </div>
        <div className="admin-form-grid">
          <div className="field"><label>甲 方奇人</label><select className="input" value={aSel ?? ""} onChange={(e) => setASel(e.target.value ? Number(e.target.value) : null)}><option value="">选择奇人…</option>{fighters.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}</select></div>
          <div className="field"><label>乙 方奇人</label><select className="input" value={bSel ?? ""} onChange={(e) => setBSel(e.target.value ? Number(e.target.value) : null)}><option value="">选择奇人…</option>{fighters.map((f) => <option key={f.id} value={f.id}>{f.label}</option>)}</select></div>
        </div>
        <div className="admin-toolbar__actions" style={{ marginTop: 4 }}>
          <button className="btn btn-ghost" disabled={busy} onClick={runDeduction}>推演对战</button>
          <button className="btn btn-ghost" disabled={busy} onClick={runReport}>仅生成报告</button>
          <span className="muted">或 指定胜负：</span>
          <select className="input" style={{ width: 110 }} value={skipWinner} onChange={(e) => setSkipWinner(e.target.value as "A" | "B" | "draw")}>
            <option value="A">甲胜</option>
            <option value="B">乙胜</option>
            <option value="draw">和局</option>
          </select>
          <button className="btn btn-primary" disabled={busy} onClick={runSkip}>指定胜负 → 猜词</button>
        </div>
        {report !== null && (
          <div className="story-view" style={{ marginTop: 14 }}>
            <div className="panel__head">
              <h3>战前讨论报告</h3>
              <span className="muted">仅讨论，未推演、未落库</span>
            </div>
            {report ? (
              <p className="story-view__text" style={{ whiteSpace: "pre-wrap" }}>{report}</p>
            ) : (
              <p className="muted">（讨论失败，未生成报告）</p>
            )}
          </div>
        )}
      </section>

      {/* 猜词 */}
      <section className="panel">
        <div className="panel__head">
          <h3>猜词测试</h3>
          <span className="muted">载入一场测试行迹，逐次提交猜测看卡片</span>
        </div>
        <div className="tbl-list">
          {battles.map((b) => (
            <div className="tbl-row" key={b.id}>
              <span className="tbl-col mono">#{b.id}</span>
              <span className="tbl-col tbl-col--main">
                <b>{b.fighter_a}</b> <i>对</i> <b>{b.fighter_b}</b>
                {b.winner_fighter && <small>胜者：{b.winner_fighter}（{b.winner}）</small>}
              </span>
              <span className="tbl-col"><span className={`status-chip status-chip--${b.status}`}>{statusLabel(b.status)}</span></span>
              <span className="tbl-col mono">{b.guess_total > 0 ? `${crackedCount(b)}/${b.guess_total} 看破 · ${b.guess_attempts_used}/${b.guess_attempts_max} 次` : "无猜词"}</span>
              <span className="tbl-col tbl-actions">
                <button className="btn btn-ghost btn-icon btn-sm" onClick={() => openDetail(b, "battle")} title="查看 / 猜词"><EyeIcon size={14} /></button>
                <button className="btn btn-danger btn-icon btn-sm" onClick={() => removeBattle(b)} title="删除"><TrashIcon size={14} /></button>
              </span>
            </div>
          ))}
        </div>
        {battles.length === 0 && <p className="muted">暂无测试行迹。</p>}
      </section>

      {selected && (
        <div className="modal-overlay" onClick={() => setSelected(null)}>
          <div className="modal modal--wide modal--xl" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <div className="modal__head">
              <h3>测试行迹 #{selected.id}</h3>
              <button className="modal__close" onClick={() => setSelected(null)} aria-label="关闭"><XIcon size={16} /></button>
            </div>
            <div className="admin-tabs modal-tabs">
              <button className={detailTab === "battle" ? "is-active" : ""} onClick={() => setDetailTab("battle")}>对决</button>
              <button className={detailTab === "guess" ? "is-active" : ""} onClick={() => setDetailTab("guess")}>猜词</button>
            </div>
            {detailTab === "battle" ? (
              <>
                <p className="muted">
                  <b>{selected.user_a}</b> 的 <b>{selected.fighter_a}</b> 对 <b>{selected.user_b}</b> 的 <b>{selected.fighter_b}</b>
                  {" "}· {statusLabel(selected.status)}
                  {selected.winner_fighter && <> · 胜者：{selected.winner_fighter}</>}
                </p>
                {selected.story && selected.status === "done" && <StoryView story={selected.story} />}
                {selected.status === "pending" && <p className="muted">推演进行中，稍后刷新查看结果…</p>}
                {selected.status === "failed" && <p className="err">推演失手：{String(selected.story?.error_message ?? "未知原因")}</p>}
                <div className="modal__foot">
                  <TracePanel battleId={selected.id} />
                </div>
              </>
            ) : (
              <>
                <p className="muted">
                  {selected.guess_total > 0
                    ? `${crackedCount(selected)}/${selected.guess_total} 门已看破 · ${selected.guess_attempts_used}/${selected.guess_attempts_max} 次`
                    : "本场无猜词"}
                </p>
                {selected.guess_total > 0 && (
                  <>
                    <GuessBoard cards={selected.guess_cards ?? []} />
                    <GuessMatrix cards={selected.guess_cards ?? []} />
                    {selected.guess_history.length > 0 && (
                      <ul className="guess-feed" style={{ marginBottom: 12 }}>
                        {selected.guess_history.map((t, i) => <li key={i}>{t}</li>)}
                      </ul>
                    )}
                    {selected.guess_state !== "done" && selected.guess_attempts_used < selected.guess_attempts_max ? (
                      <div className="admin-toolbar__actions">
                        <input className="input" style={{ flex: 1 }} value={guessText} onChange={(e) => setGuessText(e.target.value)} placeholder="道出你从行迹中看到的线索…" />
                        <button className="btn btn-primary" disabled={busy || !guessText.trim()} onClick={submitGuess}>提交猜词</button>
                      </div>
                    ) : (
                      <p className="muted">已 {selected.guess_hit ? "看破逆转" : "揭示"}：{selected.guess_hit ? "全部命中，胜负改写" : `未全破，已用 ${selected.guess_attempts_used} 次`}。</p>
                    )}
                  </>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
