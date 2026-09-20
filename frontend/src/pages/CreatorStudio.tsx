import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api } from "../api";
import { PencilIcon, PlusIcon, TrashIcon } from "../components/icons";
import { EmptyScroll, SealStamp } from "../components/Ornaments";

type Kind = "ability" | "character";
type Ability = { id: string; name: string; effect: string; detail: string };
type Character = { id: string; name: string; bio: string; ability_ids: string[] };
type Editing =
  | { kind: "ability"; value: Ability; isNew: boolean }
  | { kind: "character"; value: Character; isNew: boolean };

const EMPTY: Record<Kind, Ability | Character> = {
  ability: { id: "", name: "", effect: "", detail: "" },
  character: { id: "", name: "", bio: "", ability_ids: [] },
};

function ShortText({ value, limit = 120, className }: { value: string; limit?: number; className: string }) {
  const [expanded, setExpanded] = useState(false);
  const folded = value.length > limit && !expanded;
  return <p className={className}>{folded ? `${value.slice(0, limit)}...` : value}{value.length > limit && <button className="creator-entry__expand" onClick={() => setExpanded((current) => !current)}>{expanded ? "收起" : "展开"}</button>}</p>;
}

export default function CreatorStudio() {
  const [abilities, setAbilities] = useState<Ability[]>([]);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [activeKind, setActiveKind] = useState<Kind>("character");
  const [editing, setEditing] = useState<Editing | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    const [a, c] = await Promise.all([api<Ability[]>("/creator/abilities"), api<Character[]>("/creator/characters")]);
    setAbilities(a); setCharacters(c);
  }, []);
  useEffect(() => { void load().catch((cause: Error) => setError(cause.message)); }, [load]);

  const abilityNames = useMemo(() => new Map(abilities.map((ability) => [ability.id, ability.name])), [abilities]);
  const openEditor = (kind: Kind, value: Ability | Character, isNew = false) => {
    setError(""); setNotice("");
    setEditing({ kind, value: structuredClone(value) as never, isNew } as Editing);
  };
  const create = (kind: Kind) => openEditor(kind, EMPTY[kind], true);
  const update = (patch: Record<string, unknown>) => setEditing((current) => current ? { ...current, value: { ...current.value, ...patch } } as Editing : null);

  const save = async () => {
    if (!editing) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const base = editing.kind === "ability" ? "/creator/abilities" : "/creator/characters";
      const body = editing.kind === "ability"
        ? { name: editing.value.name, effect: editing.value.effect, detail: editing.value.detail }
        : { name: editing.value.name, bio: editing.value.bio, ability_ids: editing.value.ability_ids };
      const saved = await api<Ability | Character>(editing.isNew ? base : `${base}/${editing.value.id}`, { method: editing.isNew ? "POST" : "PUT", body: JSON.stringify(body) });
      setEditing({ kind: editing.kind, value: saved as never, isNew: false } as Editing);
      await load(); setNotice("已保存");
    } catch (cause) {
      setError(cause instanceof ApiError && cause.status === 409 ? "名称已存在，请换一个名称。" : cause instanceof Error ? cause.message : "保存失败");
    } finally { setBusy(false); }
  };

  const remove = async (kind: Kind, id: string, name: string) => {
    if (!id || !window.confirm(`确认删除「${name || "未命名"}」？`)) return;
    setBusy(true); setError("");
    try { await api(`/creator/${kind === "ability" ? "abilities" : "characters"}/${id}`, { method: "DELETE" }); setEditing(null); await load(); setNotice("已删除"); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "删除失败"); }
    finally { setBusy(false); }
  };

  const field = (label: string, key: string, max: number, rows = 1) => {
    const value = String((editing?.value as Record<string, unknown> | undefined)?.[key] ?? "");
    return <label className="field"><span>{label}<small>{value.length}/{max}</small></span>{rows > 1
      ? <textarea className="textarea" rows={rows} maxLength={max} disabled={busy} value={value} onChange={(event) => update({ [key]: event.target.value })} />
      : <input className="input" maxLength={max} disabled={busy} value={value} onChange={(event) => update({ [key]: event.target.value })} />}</label>;
  };

  if (editing) {
    const isAbility = editing.kind === "ability";
    const character = editing.kind === "character" ? editing.value : EMPTY.character as Character;
    return <section className="creator-studio creator-editor"><header className="creator-hero"><div><h1>{editing.isNew ? "新建" : "编辑"}{isAbility ? "奇术" : "奇人"}</h1><p>{isAbility ? "记录一门可供小天下集使用的奇术。" : "记录姓名、介绍，并绑定自己拥有的奇术。"}</p></div><button className="btn btn-ghost" disabled={busy} onClick={() => setEditing(null)}>取消</button></header>{(error || notice) && <p className={error ? "creator-alert" : "creator-notice"}>{error || notice}</p>}<div className="creator-editor__sheet"><div className="creator-form">{field("名字", "name", isAbility ? 10 : 30)}{isAbility ? <>{field("效果", "effect", 50, 3)}{field("详述", "detail", 500, 5)}</> : <>{field("介绍", "bio", 500, 7)}<fieldset className="creator-equipment"><legend>绑定奇术 <small>{character.ability_ids.length}/4</small></legend>{abilities.length ? <div className="creator-equipment__list">{abilities.map((ability) => <label key={ability.id}><input type="checkbox" checked={character.ability_ids.includes(ability.id)} disabled={busy || (!character.ability_ids.includes(ability.id) && character.ability_ids.length >= 4)} onChange={() => update({ ability_ids: character.ability_ids.includes(ability.id) ? character.ability_ids.filter((id) => id !== ability.id) : [...character.ability_ids, ability.id] })} /><span><b>{ability.name}</b><small>{ability.effect}</small></span></label>)}</div> : <p className="muted">尚未创建奇术。</p>}</fieldset></>}</div><div className="creator-canvas__actions"><button className="btn btn-primary" disabled={busy} onClick={() => void save()}>保存</button>{!editing.isNew && <button className="btn btn-danger" disabled={busy} onClick={() => void remove(editing.kind, editing.value.id, editing.value.name)}><TrashIcon size={14} /> 删除</button>}</div></div></section>;
  }

  const isCharacterTab = activeKind === "character";
  const actions = (kind: Kind, item: Ability | Character) => <div className="creator-entry__actions"><button className="btn btn-ghost btn-icon" title="编辑" aria-label={`编辑 ${item.name}`} disabled={busy} onClick={() => openEditor(kind, item)}><PencilIcon size={15} /></button><button className="btn btn-danger btn-icon" title="删除" aria-label={`删除 ${item.name}`} disabled={busy} onClick={() => void remove(kind, item.id, item.name)}><TrashIcon size={15} /></button></div>;
  return <section className="creator-studio creator-codex"><header className="creator-hero"><div><h1>异闻录</h1><p>收录自己的奇人、奇术，并为小天下集准备可用阵容。</p></div><div className="creator-hero__actions"><Link className="muted" to="/home">返回首页</Link><Link className="btn btn-ghost" to="/scenarios">浏览小天下集</Link></div></header>{(error || notice) && <p className={error ? "creator-alert" : "creator-notice"}>{error || notice}</p>}<div className="creator-tabs-native" role="tablist" aria-label="异闻录篇章"><button type="button" role="tab" aria-selected={isCharacterTab} className={isCharacterTab ? "is-active" : ""} onClick={() => setActiveKind("character")}>奇人篇<span>{characters.length}</span></button><button type="button" role="tab" aria-selected={!isCharacterTab} className={!isCharacterTab ? "is-active" : ""} onClick={() => setActiveKind("ability")}>奇术篇<span>{abilities.length}</span></button></div><section className="creator-chapter"><header className="creator-chapter__head"><div><h2>{isCharacterTab ? "奇人篇" : "奇术篇"}</h2><p>{isCharacterTab ? "姓名、介绍与已绑定奇术" : "奇术效果与详述"}</p></div><button className="btn btn-primary" disabled={busy} onClick={() => create(activeKind)}><PlusIcon size={15} /> 新建{isCharacterTab ? "奇人" : "奇术"}</button></header><div className={isCharacterTab ? "creator-character-grid" : "creator-ability-grid"}>{isCharacterTab ? characters.map((item, index) => <article className="creator-character-card" key={item.id}><div className="creator-character-card__head"><h3><SealStamp char={String(index + 1)} size={26} className="creator-character-card__seal" />{item.name}</h3><span className="creator-character-card__count">{item.ability_ids.length} 门奇术</span></div><ShortText value={item.bio || "暂无介绍"} className="creator-character-card__bio" /><div className="creator-character-card__chips">{item.ability_ids.length ? item.ability_ids.map((id) => <span className="chip chip--ability" key={id}>{abilityNames.get(id) ?? "已删除奇术"}</span>) : <span className="creator-character-card__empty">尚未绑定奇术</span>}</div><div className="creator-character-card__foot"><span>私有条目</span>{actions("character", item)}</div></article>) : abilities.map((item) => <article className="creator-ability-card" key={item.id}><div className="creator-ability-card__head"><h3>{item.name}</h3>{actions("ability", item)}</div><p className="creator-ability-card__effect">{item.effect}</p><ShortText value={item.detail || "暂无详述"} className="creator-ability-card__detail" /></article>)}</div>{(isCharacterTab ? characters : abilities).length === 0 && <div className="empty empty--scroll creator-chapter__empty"><EmptyScroll size={140} /><h3>尚未收录{isCharacterTab ? "奇人" : "奇术"}</h3><p>{isCharacterTab ? "写下第一位奇人，绑定奇术后即可在小天下集出战。" : "先记下几门奇术，才好为奇人装配招式。"}</p></div>}</section></section>;
}
