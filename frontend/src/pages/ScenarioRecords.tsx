import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { SealStamp } from "../components/Ornaments";
import { BookIcon, ChevronLeftIcon, ChevronRightIcon } from "../components/icons";
import { ScenarioManuscript } from "../components/ScenarioNarrative";
import { isInProgress, type ScenarioHistoryItem } from "../scenarioModel";

type Challenge = {
  id: string;
  status: string;
  challenge_number: number;
  is_preview?: boolean;
  roster: { character_name: string };
  challenger: { character_name: string };
  messages: { role: string; text?: string; challenger_text?: string; guardian_text?: string; omniscient?: string; created_at?: string }[];
  won: boolean | null;
  viewer_role?: "challenger" | "owner";
  derived?: { achieved?: boolean; reason?: string };
};
type RosterContext = {
  scenario: { name: string; subtitle: string; slug: string };
  roster: { character_name: string };
  viewer_role?: "challenger" | "owner";
  my_challenges: ScenarioHistoryItem[];
  owner_challenges?: ScenarioHistoryItem[];
};

const verdictOf = (item: ScenarioHistoryItem): { text: string; tone: string } => {
  if (isInProgress(item.status)) return { text: "尚未成卷", tone: "is-pending" };
  if (item.status === "failed") return { text: "未能成卷", tone: "is-void" };
  return item.won ? { text: "胜", tone: "is-won" } : { text: "负", tone: "is-lost" };
};

/**
 * 记录阅读页（账册行阅）：本阵容的逐局簿册——每局一行，选中的一局就地展开为行迹书页。
 * 单主视角、上帝门控与对战页同规则（未看破全部只见己方正文；守方始终只见自己）。
 */
export default function ScenarioRecords() {
  const { scenarioSlug, rosterId } = useParams<{ scenarioSlug: string; rosterId: string }>();
  const [params, setParams] = useSearchParams();
  const [context, setContext] = useState<RosterContext | null>(null);
  const [detail, setDetail] = useState<Challenge | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState("");

  const selected = params.get("run");

  useEffect(() => {
    if (!scenarioSlug || !rosterId) return;
    let alive = true;
    api<RosterContext>(`/scenarios/${scenarioSlug}/rosters/${rosterId}`)
      .then((data) => alive && setContext(data))
      .catch((cause: Error) => alive && setError(cause.message));
    return () => {
      alive = false;
    };
  }, [scenarioSlug, rosterId]);

  const owner = context?.viewer_role === "owner";
  // 守方视角：他人挑战 + 自己的创作台试炼（预览局），按时间倒序混排
  const items = owner
    ? [
        ...(context?.owner_challenges ?? []),
        ...(context?.my_challenges ?? []).filter((item) => item.is_preview),
      ].sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""))
    : context?.my_challenges ?? [];
  const newest = items.length ? items[0].id : null;
  const activeId = selected ?? newest;

  useEffect(() => {
    if (!activeId) {
      setDetail(null);
      return;
    }
    let alive = true;
    setLoadingDetail(true);
    setDetail(null);
    api<Challenge>(`/scenario-challenges/${activeId}`)
      .then((data) => alive && setDetail(data))
      .catch((cause: Error) => alive && setError(cause.message))
      .finally(() => alive && setLoadingDetail(false));
    return () => {
      alive = false;
    };
  }, [activeId]);

  if (!context)
    return error ? <p className="err">{error}</p> : <div className="skeleton" style={{ height: 320 }} />;

  const backHref = `/scenarios/${scenarioSlug}/rosters/${rosterId}`;
  const own: "challenger" | "guardian" = owner ? "guardian" : "challenger";
  const ownLabel = owner ? detail?.roster.character_name ?? "" : detail?.challenger.character_name ?? "";
  const inProgress = detail ? isInProgress(detail.status) : false;

  return (
    <section className="panel world-story scenario-challenge">
      <Link className="scenario-back" to={backHref} aria-label="退出并返回阵容详情">
        <ChevronLeftIcon size={20} />
      </Link>
      <header className="scenario-challenge__masthead">
        <div>
          <h1>{context.scenario.name} · 往期记录</h1>
          <p className="muted">{context.scenario.subtitle}</p>
        </div>
        <span className="muted">
          <BookIcon size={14} /> 共 {items.length} 局
        </span>
      </header>
      {!items.length ? (
        <div className="records-empty">
          <p className="muted">尚无记录。完成第一场挑战后，本册会从第一笔写起。</p>
        </div>
      ) : (
        <div className="records-ledger" role="list">
          {[...items].reverse().map((item) => {
            const open = item.id === activeId;
            const verdict = verdictOf(item);
            return (
              <div className={`records-row${open ? " is-open" : ""}`} role="listitem" key={item.id}>
                <button
                  type="button"
                  className="records-row__hit"
                  aria-expanded={open}
                  onClick={() => setParams(open ? {} : { run: item.id }, { replace: true })}
                >
                  <span className="records-row__no">
                    {item.is_preview ? "创作台试炼" : `第 ${item.challenge_number} 次推演`}
                  </span>
                  {owner && !item.is_preview && item.challenger_character_name && (
                    <span className="records-row__who">{item.challenger_character_name}</span>
                  )}
                  <span className={`records-row__verdict ${verdict.tone}`}>{verdict.text}</span>
                  <span className="records-row__arrow" aria-hidden="true">
                    <ChevronRightIcon size={16} />
                  </span>
                </button>
                {open && (
                  <div className="records-row__folio">
                    {loadingDetail && !detail ? (
                      <div className="skeleton" style={{ height: 220 }} />
                    ) : detail ? (
                      <>
                        {inProgress && (
                          <p className="muted">
                            本局尚未成卷，实时战况在 <Link to={backHref}>对战页</Link>。
                          </p>
                        )}
                        <ScenarioManuscript
                          messages={detail.messages}
                          own={own}
                          ownLabel={ownLabel}
                          title={`第 ${detail.challenge_number} 次推演`}
                          note={detail.won === null ? "尚未成卷" : "本场结局已记录"}
                          emptyText="奇术比对完成后，整场推演将一次成卷。"
                        />
                        {detail.won !== null && (
                          <div className={`records-verdict ${detail.won ? "is-won" : "is-lost"}`}>
                            <span className="records-verdict__seal">
                              <SealStamp char={detail.won ? "胜" : "负"} size={34} />
                            </span>
                            <div>
                              <strong>{detail.won ? "挑战目标已达成" : "挑战目标未达成"}</strong>
                              {detail.derived?.reason && <p>{detail.derived.reason}</p>}
                            </div>
                          </div>
                        )}
                      </>
                    ) : null}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
      {error && <p className="err">{error}</p>}
    </section>
  );
}