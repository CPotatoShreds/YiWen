import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { SealStamp } from "../components/Ornaments";
import { BookIcon, ChevronRightIcon } from "../components/icons";
import { ScenarioManuscript } from "../components/ScenarioNarrative";
import { BackButton } from "../components/PageShell";
import { isInProgress, type ScenarioHistoryItem } from "../scenarioModel";
import { formatShortDateTime } from "../datetime";

type Challenge = {
  id: string;
  status: string;
  created_at?: string;
  is_trial?: boolean;
  roster: { character_name: string };
  challenger: { character_name: string };
  messages: { role: string; text?: string; challenger_text?: string; guardian_text?: string; omniscient?: string; created_at?: string }[];
  won: boolean | null;
  viewer_role?: "challenger" | "owner" | "both";
  derived?: { achieved?: boolean; reason?: string };
};
type RosterContext = {
  scenario: { name: string; subtitle: string; slug: string };
  roster: { character_name: string };
  viewer_role?: "challenger" | "owner" | "both";
  my_challenges: ScenarioHistoryItem[];
};

const verdictOf = (item: ScenarioHistoryItem): { text: string; tone: string } => {
  if (isInProgress(item.status)) return { text: "尚未成卷", tone: "is-pending" };
  if (item.status === "failed") return { text: "未能成卷", tone: "is-void" };
  return item.won ? { text: "胜", tone: "is-won" } : { text: "负", tone: "is-lost" };
};

/**
 * 记录阅读页（账册行阅）：本刻印的逐局簿册——每局一行，选中的一局就地展开为行迹书页。
 * 单主视角、推演门控与对战页同规则（未看破全部只见己方叙述；刻印始终只见自己）。
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

  // 只列当前访问者自己的对局。刻印作者在此看到的自然只有自己的试炼局——
  // 他人来打的战绩不对作者开放（作者视角只有刻印正文，见后端 challenge_detail）。
  const items = context?.my_challenges ?? [];
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
  // 视角按当前这场 challenge 的 viewer_role 定：owner 只表示「你是不是这套刻印的作者」，
  // 自己打自己的刻印会是 both，推演与双方正文一起呈。
  const own: "challenger" | "guardian" | "both" =
    detail?.viewer_role === "both" ? "both" : detail?.viewer_role === "owner" ? "guardian" : "challenger";
  const ownLabel = own === "guardian" ? detail?.roster.character_name ?? "" : detail?.challenger.character_name ?? "";
  const inProgress = detail ? isInProgress(detail.status) : false;

  return (
    <section className="panel world-story scenario-challenge">
      <BackButton to={backHref} label="退出并返回刻印详情" />
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
          <p className="muted">尚无记录。完成第一场对局后，本册会从第一笔写起。</p>
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
                  onClick={() => setParams({ run: open ? "" : item.id }, { replace: true })}
                >
                  <span className="records-row__main">
                    <strong className="records-row__who">
                      {item.challenger_character_name || "未知挑战者"}
                    </strong>
                    <small className="records-row__strategy">
                      {item.strategy || "跳过策略，由奇人自行应对"}
                    </small>
                  </span>
                  <span className="records-row__time">{formatShortDateTime(item.created_at)}</span>
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
                          guardianLabel={detail.roster.character_name}
                          title="本场推演"
                          note={detail.won === null ? "尚未成卷" : "本场结局已记录"}
                          emptyText="奇术比对完成后，整场推演将一次成卷。"
                        />
                        {detail.won !== null && (
                          <div className={`records-verdict ${detail.won ? "is-won" : "is-lost"}`}>
                            <span className="records-verdict__seal">
                              <SealStamp char={detail.won ? "胜" : "负"} size={34} />
                            </span>
                            <div>
                              <strong>{detail.won ? "对局目标已达成" : "对局目标未达成"}</strong>
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
