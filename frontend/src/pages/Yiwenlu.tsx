import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { ApiError, api } from "../api";
import { BookIcon, ChevronLeftIcon, ChevronRightIcon, PencilIcon, PlusIcon, TrashIcon, XIcon } from "../components/icons";
import { EmptyScroll, SealStamp } from "../components/Ornaments";
import PageShell from "../components/PageShell";

type Kind = "character" | "ability";
type Ability = { id: string; name: string; effect: string; detail: string };
type Character = { id: string; name: string; bio: string; ability_ids: string[] };
type CharacterDetail = Character & { abilities: Ability[] };

/** 一位奇人可装配的奇术上限，与后端约束一致。装配是无序集合，顺序只作展示。 */
const SLOTS = 4;
const LABEL: Record<Kind, string> = { character: "奇人", ability: "奇术" };
const SEGMENT: Record<Kind, string> = { character: "characters", ability: "abilities" };
const UNIT: Record<Kind, string> = { character: "位", ability: "门" };
const LIMIT = { name: { character: 30, ability: 10 }, bio: 500, effect: 50, detail: 500 };

const BLANK = { name: "", bio: "", effect: "", detail: "", ability_ids: [] as string[] };
type Form = typeof BLANK;

const pathOf = (kind: Kind, id?: string | null) => (id ? `/yiwenlu/${SEGMENT[kind]}/${id}` : `/yiwenlu?p=${kind}`);

/**
 * 异闻录工作台：左栏名册（奇人篇 / 奇术篇），右栏同一张卷面查看与编辑。
 * 奇人 ↔ 奇术互相可点：奇人卷上的奇术槽跳到奇术卷，奇术卷标出载于哪几位奇人名帖。
 */
export default function Yiwenlu({ kind: routeKind }: { kind?: Kind }) {
  const { id: urlId } = useParams();
  const navigate = useNavigate();
  const [params] = useSearchParams();

  const [abilities, setAbilities] = useState<Ability[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [detail, setDetail] = useState<CharacterDetail | null>(null);
  const [revision, setRevision] = useState(0);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const [editing, setEditing] = useState(false);
  const [isNew, setIsNew] = useState(false);
  const [form, setForm] = useState<Form>(BLANK);
  /** 来处栈：互跳时压入上一个落点，右栏顶部的「← 回到 X」出栈返回。 */
  const [trail, setTrail] = useState<{ kind: Kind; id: string; name: string }[]>([]);
  const activeRef = useRef<HTMLButtonElement>(null);

  const paramKind = params.get("p") === "ability" ? "ability" : params.get("p") === "character" ? "character" : null;
  const kind: Kind = routeKind ?? paramKind ?? "character";

  const load = useCallback(async () => {
    const [a, c] = await Promise.all([api<Ability[]>("/creator/abilities"), api<Character[]>("/creator/characters")]);
    setAbilities(a);
    setCharacters(c);
  }, []);

  useEffect(() => {
    void load()
      .then(() => setError(""))
      .catch((cause: Error) => setError(cause.message))
      .finally(() => setReady(true));
  }, [load, revision]);

  /* ---------- 选中项：URL 是唯一事实来源 ---------- */
  const list = kind === "character" ? characters : abilities;
  const fromUrl = routeKind === kind && urlId && list.some((item) => item.id === urlId) ? urlId : null;
  const selectedId = fromUrl ?? list[0]?.id ?? null;
  const current = selectedId ? list.find((item) => item.id === selectedId) ?? null : null;
  const currentCharacter = kind === "character" ? (current as Character | null) : null;
  const currentAbility = kind === "ability" ? (current as Ability | null) : null;
  const ordinal = selectedId ? list.findIndex((item) => item.id === selectedId) + 1 : 0;

  // 奇人的装配列表用详情接口（顺序与后端 position 一致）；详情未到时退回名册里的 id 映射
  useEffect(() => {
    if (kind !== "character" || !selectedId) {
      setDetail(null);
      return;
    }
    let alive = true;
    api<CharacterDetail>(`/creator/characters/${selectedId}`)
      .then((loaded) => { if (alive) setDetail(loaded); })
      .catch(() => { if (alive) setDetail(null); });
    return () => { alive = false; };
  }, [kind, selectedId, revision]);

  const equipped = useMemo<Ability[]>(() => {
    if (!currentCharacter) return [];
    if (detail && detail.id === currentCharacter.id) return detail.abilities;
    return currentCharacter.ability_ids.flatMap((id) => abilities.filter((item) => item.id === id));
  }, [currentCharacter, detail, abilities]);

  /** 这门奇术载于哪几位奇人名帖——删奇术会级联摘除，必须先摆出来。 */
  const carriers = currentAbility
    ? characters.filter((item) => item.ability_ids.includes(currentAbility.id))
    : [];

  // 名册在窄屏折成横向条：当前项保持在可见区，免得「我在看谁」丢失
  useEffect(() => { activeRef.current?.scrollIntoView({ block: "nearest", inline: "nearest" }); }, [selectedId, kind, list.length]);

  /* ---------- 编辑 ---------- */
  const dirty = editing && (isNew
    ? form.name.trim() !== "" || form.bio.trim() !== "" || form.effect.trim() !== "" || form.detail.trim() !== "" || form.ability_ids.length > 0
    : current !== null && (form.name !== current.name
      || (kind === "character" && (form.bio !== currentCharacter?.bio || form.ability_ids.join(",") !== (currentCharacter?.ability_ids ?? []).join(",")))
      || (kind === "ability" && (form.effect !== currentAbility?.effect || form.detail !== currentAbility?.detail))));

  const patch = (next: Partial<Form>) => setForm((prev) => ({ ...prev, ...next }));

  const guarded = (action: () => void) => {
    if (editing && dirty && !window.confirm("放弃未保存的修改？")) return;
    action();
  };

  const enterEdit = () => {
    if (!current) return;
    setError("");
    setNotice("");
    setForm({
      name: current.name,
      bio: currentCharacter?.bio ?? "",
      effect: currentAbility?.effect ?? "",
      detail: currentAbility?.detail ?? "",
      ability_ids: currentCharacter ? [...currentCharacter.ability_ids] : [],
    });
    setIsNew(false);
    setEditing(true);
  };

  const enterCreate = (target: Kind = kind) => {
    if (editing && dirty && !window.confirm("放弃未保存的修改？")) return;
    setError("");
    setNotice("");
    setForm({ ...BLANK });
    setIsNew(true);
    setEditing(true);
    if (target !== kind) navigate(`/yiwenlu?p=${target}`);
  };

  const cancelEdit = () => {
    if (dirty && !window.confirm("放弃未保存的修改？")) return;
    setEditing(false);
    setIsNew(false);
    setError("");
  };

  const go = (target: Kind, id: string) => guarded(() => {
    if (target === kind && id === selectedId) return;
    if (current) setTrail((prev) => [...prev.slice(-4), { kind, id: current.id, name: current.name }]);
    navigate(pathOf(target, id));
  });

  const backTo = (entry: { kind: Kind; id: string }) => guarded(() => {
    setTrail((prev) => prev.slice(0, -1));
    navigate(pathOf(entry.kind, entry.id));
  });

  const switchKind = (target: Kind) => guarded(() => {
    if (target === kind) return;
    setTrail([]);
    navigate(`/yiwenlu?p=${target}`);
  });

  const toggleAbility = (id: string) => setForm((prev) => (
    prev.ability_ids.includes(id)
      ? { ...prev, ability_ids: prev.ability_ids.filter((item) => item !== id) }
      : prev.ability_ids.length >= SLOTS ? prev : { ...prev, ability_ids: [...prev.ability_ids, id] }
  ));

  const save = async () => {
    if (!form.name.trim()) {
      setError(`先给${LABEL[kind]}起个名字。`);
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    const body = kind === "character"
      ? { name: form.name, bio: form.bio, ability_ids: form.ability_ids }
      : { name: form.name, effect: form.effect, detail: form.detail };
    try {
      const saved = await api<{ id: string }>(
        isNew ? `/creator/${SEGMENT[kind]}` : `/creator/${SEGMENT[kind]}/${selectedId}`,
        { method: isNew ? "POST" : "PUT", body: JSON.stringify(body) },
      );
      setEditing(false);
      setIsNew(false);
      setRevision((value) => value + 1);
      setNotice(isNew ? `已收录${LABEL[kind]}` : "已保存");
      if (isNew || saved.id !== selectedId) navigate(pathOf(kind, saved.id));
    } catch (cause) {
      setError(cause instanceof ApiError && cause.status === 409 ? "名称已存在，请换一个名称。" : cause instanceof Error ? cause.message : "保存失败");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (!current) return;
    const prompt = kind === "ability" && carriers.length
      ? `删除「${current.name}」？\n\n它已被 ${carriers.length} 位奇人装配（${carriers.slice(0, 3).map((item) => item.name).join("、")}${carriers.length > 3 ? " 等" : ""}），删除后会从他们名帖上一并摘除。`
      : kind === "ability"
        ? `确认删除「${current.name}」？还没有奇人装配它。`
        : `确认删除「${current.name}」？\n\n删除后不能再拿他去立新异闻、发起新对局；已发布的异闻不受影响。`;
    if (!window.confirm(prompt)) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api(`/creator/${SEGMENT[kind]}/${current.id}`, { method: "DELETE" });
      setEditing(false);
      setIsNew(false);
      setTrail([]);
      setNotice(`已删除${LABEL[kind]}`);
      navigate(`/yiwenlu?p=${kind}`);
      setRevision((value) => value + 1);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "删除失败");
    } finally {
      setBusy(false);
    }
  };

  /* ---------- 整册皆空 ---------- */
  if (ready && !characters.length && !abilities.length) {
    return (
      <section className="codex codex--virgin">
        <div className="codex__virgin">
          <EmptyScroll size={150} />
          <h2 className="section-title">异闻录尚是空白</h2>
          <p>奇人是出战的人，奇术是他的手段。先写下第一位奇人，或先记一门奇术——两者随后可在名帖上互相装配。</p>
          <div className="codex__virgin-actions">
            <button className="btn btn-primary" disabled={busy} onClick={() => enterCreate("character")}><PlusIcon size={15} /> 写一位奇人</button>
            <button className="btn btn-ghost" disabled={busy} onClick={() => enterCreate("ability")}><PlusIcon size={15} /> 记一门奇术</button>
          </div>
          {error && <p className="err" role="alert">{error}</p>}
        </div>
      </section>
    );
  }

  const sealChar = (editing ? form.name : current?.name ?? "").slice(0, 1) || (kind === "character" ? "奇" : "术");
  const nameMax = LIMIT.name[kind];
  const slotsShown = editing && kind === "character" ? form.ability_ids.length : equipped.length;
  const emptySlots = Math.max(0, SLOTS - slotsShown);
  const lastTrail = trail[trail.length - 1];

  return (
    <PageShell
      width="wide"
      title="异闻录"
      icon={<BookIcon size={19} />}
      subtitle={<span>奇人 <b>{characters.length}</b> 位 · 奇术 <b>{abilities.length}</b> 门，皆为小天下集所用。</span>}
      back={{ to: "/home", label: "返回首页" }}
    >
      <div className="codex__body">
        {/* ---------- 左：名册 ---------- */}
        <aside className="codex__rail">
          <div className="codex__tabs" role="tablist" aria-label="异闻录篇章">
            {(["character", "ability"] as Kind[]).map((tab) => (
              <button
                key={tab}
                type="button"
                role="tab"
                aria-selected={kind === tab}
                className={`codex__tab${kind === tab ? " is-active" : ""}`}
                onClick={() => switchKind(tab)}
              >
                {tab === "character" ? "奇人篇" : "奇术篇"}
                <span>{tab === "character" ? characters.length : abilities.length}</span>
              </button>
            ))}
          </div>
          <nav className="codex__list" aria-label={`${LABEL[kind]}名册`}>
            {list.length === 0 ? (
              <p className="codex__list-empty">这一篇还没有{LABEL[kind]}。</p>
            ) : kind === "character" ? (
              characters.map((entry) => (
                <button
                  type="button"
                  key={entry.id}
                  ref={entry.id === selectedId ? activeRef : undefined}
                  className={`codex__item${entry.id === selectedId ? " is-active" : ""}`}
                  aria-current={entry.id === selectedId ? "true" : undefined}
                  onClick={() => go("character", entry.id)}
                >
                  <SealStamp char={entry.name.slice(0, 1) || "奇"} size={22} className="codex__item-seal" />
                  <span className="codex__item-body">
                    <span className="codex__item-name">{entry.name}</span>
                    <span className="codex__item-meta">奇术 {entry.ability_ids.length}/{SLOTS}</span>
                  </span>
                </button>
              ))
            ) : (
              abilities.map((entry) => (
                <button
                  type="button"
                  key={entry.id}
                  ref={entry.id === selectedId ? activeRef : undefined}
                  className={`codex__item${entry.id === selectedId ? " is-active" : ""}`}
                  aria-current={entry.id === selectedId ? "true" : undefined}
                  onClick={() => go("ability", entry.id)}
                >
                  <SealStamp char={entry.name.slice(0, 1) || "术"} size={22} className="codex__item-seal" />
                  <span className="codex__item-body">
                    <span className="codex__item-name">{entry.name}</span>
                    <span className="codex__item-meta">{entry.effect || "尚未写下效果"}</span>
                  </span>
                </button>
              ))
            )}
          </nav>
          <div className="codex__rail-foot">
            <button className="btn btn-primary" disabled={busy} onClick={() => enterCreate()}>
              <PlusIcon size={14} /> 新建{LABEL[kind]}
            </button>
          </div>
        </aside>

        {/* ---------- 右：查看 / 编辑一体 ---------- */}
        <div className="codex__main">
          {lastTrail && !isNew && (
            /* 这不是「返回上一层」，而是同一页内退回刚看过的那一条，所以用文字形态 */
            <button type="button" className="nav-inline" onClick={() => backTo(lastTrail)} aria-label={`回到 ${lastTrail.name}`}>
              <ChevronLeftIcon size={14} />
              <span>回到 {lastTrail.name}</span>
            </button>
          )}

          <article className="codex__sheet">
            {(error || notice) && (
              <p className={error ? "err" : "codex__notice"} role={error ? "alert" : "status"}>{error || notice}</p>
            )}

            {!editing && !current ? (
              <div className="codex__blank">
                <EmptyScroll size={120} />
                <h3>{kind === "character" ? "奇人篇尚空" : "奇术篇尚空"}</h3>
                <p>{kind === "character" ? "写下第一位奇人，再为他装配奇术。" : "记下第一门奇术，它会成为某位奇人的手段。"}</p>
                <button className="btn btn-primary" disabled={busy} onClick={() => enterCreate()}>
                  <PlusIcon size={15} /> 新建{LABEL[kind]}
                </button>
              </div>
            ) : (
              <>
                <div className="codex__head">
                  <SealStamp char={sealChar} size={46} className="codex__seal" />
                  <div className="codex__identity">
                    <p className="eyebrow">
                      {kind === "character" ? "奇人卷" : "奇术卷"}{isNew ? " · 新录" : ordinal ? ` · 第 ${ordinal} ${UNIT[kind]}` : ""}
                    </p>
                    {editing ? (
                      <input
                        className="input codex__name-input"
                        maxLength={nameMax}
                        disabled={busy}
                        value={form.name}
                        placeholder={`${LABEL[kind]}名号`}
                        aria-label="名字"
                        onChange={(event) => patch({ name: event.target.value })}
                      />
                    ) : (
                      <h2>{current?.name}</h2>
                    )}
                  </div>
                  {!editing && current && (
                    <div className="codex__actions">
                      <button
                        className="btn btn-ghost btn-icon"
                        title="编辑"
                        aria-label={`编辑 ${current.name}`}
                        disabled={busy}
                        onClick={enterEdit}
                      >
                        <PencilIcon size={15} />
                      </button>
                    </div>
                  )}
                </div>

                {editing ? (
                  <div className="codex__edit">
                    {kind === "character" ? (
                      <label className="field">
                        <span>介绍<small>{form.bio.length}/{LIMIT.bio}</small></span>
                        <textarea
                          className="textarea"
                          rows={6}
                          maxLength={LIMIT.bio}
                          disabled={busy}
                          value={form.bio}
                          placeholder="他是谁，从哪来，怕什么。"
                          onChange={(event) => patch({ bio: event.target.value })}
                        />
                      </label>
                    ) : (
                      <>
                        <label className="field">
                          <span>效果<small>{form.effect.length}/{LIMIT.effect}</small></span>
                          <textarea
                            className="textarea"
                            rows={2}
                            maxLength={LIMIT.effect}
                            disabled={busy}
                            value={form.effect}
                            placeholder="一句话说清它做什么。"
                            onChange={(event) => patch({ effect: event.target.value })}
                          />
                        </label>
                        <label className="field">
                          <span>详述<small>{form.detail.length}/{LIMIT.detail}</small></span>
                          <textarea
                            className="textarea"
                            rows={6}
                            maxLength={LIMIT.detail}
                            disabled={busy}
                            value={form.detail}
                            placeholder="它怎么使，有什么代价或破绽。"
                            onChange={(event) => patch({ detail: event.target.value })}
                          />
                        </label>
                      </>
                    )}

                    {kind === "character" && (
                      <div className="codex__section">
                        <div className="codex__section-head">
                          <h3>装配奇术</h3>
                          <span className="codex__count">{form.ability_ids.length}/{SLOTS}</span>
                        </div>
                        <div className="codex__slots">
                          {form.ability_ids.map((id) => {
                            const ability = abilities.find((item) => item.id === id);
                            return (
                              <div className="codex__slot" key={id}>
                                <span className="codex__slot-body">
                                  <b>{ability?.name ?? "已删除奇术"}</b>
                                  {ability && <small>{ability.effect}</small>}
                                </span>
                                <button
                                  type="button"
                                  className="codex__slot-remove"
                                  title="摘下"
                                  aria-label={`摘下 ${ability?.name ?? "奇术"}`}
                                  disabled={busy}
                                  onClick={() => toggleAbility(id)}
                                >
                                  <XIcon size={13} />
                                </button>
                              </div>
                            );
                          })}
                          {Array.from({ length: emptySlots }).map((_, index) => (
                            <span className="codex__slot is-empty" key={`empty-${index}`}>空位</span>
                          ))}
                        </div>
                        <p className="codex__pick-hint">
                          {form.ability_ids.length >= SLOTS ? "四门已满，先摘下一门再补。" : "点一门补入：装上的奇术就是这位奇人的手段。"}
                        </p>
                        <div className="codex__pick">
                          {abilities.filter((item) => !form.ability_ids.includes(item.id)).map((item) => (
                            <button
                              type="button"
                              key={item.id}
                              className="codex__pick-item"
                              disabled={busy || form.ability_ids.length >= SLOTS}
                              onClick={() => toggleAbility(item.id)}
                            >
                              <span className="codex__slot-body">
                                <b>{item.name}</b>
                                <small>{item.effect}</small>
                              </span>
                              <PlusIcon size={14} />
                            </button>
                          ))}
                          {abilities.length === 0 && <p className="muted">尚未记下奇术，先切到「奇术篇」写一门。</p>}
                        </div>
                      </div>
                    )}

                    <div className="codex__edit-actions">
                      {!isNew && (
                        <button className="btn btn-danger" disabled={busy} onClick={() => void remove()}>
                          <TrashIcon size={14} /> 删除
                        </button>
                      )}
                      <button className="btn btn-ghost" disabled={busy} onClick={cancelEdit}>取消</button>
                      <button className="btn btn-primary" disabled={busy} onClick={() => void save()}>
                        {isNew ? "收录" : "保存"}
                      </button>
                    </div>
                  </div>
                ) : kind === "character" && currentCharacter ? (
                  <div className="codex__view">
                    <p className="codex__bio">
                      {currentCharacter.bio.trim() ? currentCharacter.bio : <span className="muted">尚未写下介绍。</span>}
                    </p>
                    <div className="codex__section">
                      <div className="codex__section-head">
                        <h3>装配奇术</h3>
                        <span className="codex__count">{equipped.length}/{SLOTS}</span>
                      </div>
                      <div className="codex__slots">
                        {equipped.map((ability) => (
                          <button
                            type="button"
                            className="codex__slot"
                            key={ability.id}
                            onClick={() => go("ability", ability.id)}
                          >
                            <span className="codex__slot-body">
                              <b>{ability.name}</b>
                              <small>{ability.effect}</small>
                            </span>
                            <ChevronRightIcon size={14} />
                          </button>
                        ))}
                        {Array.from({ length: emptySlots }).map((_, index) => (
                          <span className="codex__slot is-empty" key={`empty-${index}`}>空位</span>
                        ))}
                      </div>
                      <p className="codex__hint">
                        {equipped.length === 0
                          ? "尚未装配。点右上铅笔补上——奇术在小天下集里就是这位奇人的手段。"
                          : equipped.length < SLOTS
                            ? "点任一门可跳到奇术卷看详述。"
                            : "四门已满。"}
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="codex__view">
                    <p className="codex__effect">{currentAbility?.effect?.trim() || <span className="muted">尚未写下效果。</span>}</p>
                    <div className="codex__section">
                      <div className="codex__section-head"><h3>详述</h3></div>
                      <p className="codex__detail">
                        {currentAbility?.detail?.trim() ? currentAbility.detail : <span className="muted">尚未写下详述。</span>}
                      </p>
                    </div>
                    <div className="codex__section">
                      <div className="codex__section-head">
                        <h3>载于名帖</h3>
                        <span className="codex__count">{carriers.length} 位</span>
                      </div>
                      {carriers.length ? (
                        <>
                          <div className="codex__carriers">
                            {carriers.map((entry) => (
                              <button
                                type="button"
                                className="codex__carrier"
                                key={entry.id}
                                onClick={() => go("character", entry.id)}
                              >
                                <SealStamp char={entry.name.slice(0, 1) || "奇"} size={20} />
                                <span>{entry.name}</span>
                                <ChevronRightIcon size={13} />
                              </button>
                            ))}
                          </div>
                          <p className="codex__hint">这门奇术被以上 {carriers.length} 位奇人共用，改名会同步到他们的名帖。</p>
                        </>
                      ) : (
                        <p className="codex__hint">还没有奇人装配它。先去「奇人篇」为某位奇人装上。</p>
                      )}
                    </div>
                  </div>
                )}
              </>
            )}
          </article>
        </div>
      </div>
    </PageShell>
  );
}
