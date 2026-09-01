import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { PencilIcon, PlusIcon, TrashIcon } from "../components/icons";
import { ApiError, api } from "../api";

type Kind = "ability" | "character";
type Component = {
  id: string;
  kind: Kind;
  name: string;
  content: Record<string, string>;
  lock_version: number;
  ability_asset_ids: string[];
};

const EMPTY = {
  ability: { name: "", effect: "待填写", detail: "" },
  character: { name: "", bio: "" },
} satisfies Record<Kind, Record<string, string>>;

function ShortText({ value, limit = 120, className = "creator-entry__text" }: { value: string; limit?: number; className?: string }) {
  const [expanded, setExpanded] = useState(false);
  const folded = value.length > limit && !expanded;
  return <p className={className}>{folded ? `${value.slice(0, limit)}...` : value}{value.length > limit && <button className="creator-entry__expand" onClick={() => setExpanded(!expanded)}>{expanded ? "收起" : "展开"}</button>}</p>;
}

export default function CreatorStudio() {
  const [abilities, setAbilities] = useState<Component[]>([]);
  const [characters, setCharacters] = useState<Component[]>([]);
  const [activeKind, setActiveKind] = useState<Kind>("character");
  const [editing, setEditing] = useState<Component | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>(EMPTY.ability);
  const [equipped, setEquipped] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    try {
      const [abilityItems, characterItems] = await Promise.all([
        api<Component[]>("/creator/abilities"),
        api<Component[]>("/creator/characters"),
      ]);
      setAbilities(abilityItems);
      setCharacters(characterItems);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "读取异闻录失败");
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const abilityNames = useMemo(() => new Map(abilities.map((ability) => [ability.id, ability.name])), [abilities]);
  const openEditor = (component: Component) => {
    setError("");
    setNotice("");
    setEditing(component);
    setDraft(component.content);
    setEquipped(component.ability_asset_ids);
  };

  const create = async (kind: Kind) => {
    setBusy(true);
    setError("");
    try {
      const component = await api<Component>(`/creator/${kind === "ability" ? "abilities" : "characters"}`, {
        method: "POST",
        body: JSON.stringify(EMPTY[kind]),
      });
      await load();
      openEditor(component);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "新建失败");
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    if (!editing) return;
    setBusy(true);
    setError("");
    try {
      const body = editing.kind === "character"
        ? { ...draft, ability_asset_ids: equipped, lock_version: editing.lock_version }
        : { ...draft, lock_version: editing.lock_version };
      const saved = await api<Component>(`/creator/${editing.kind === "ability" ? "abilities" : "characters"}/${editing.id}`, {
        method: "PUT",
        body: JSON.stringify(body),
      });
      setEditing(saved);
      setDraft(saved.content);
      setEquipped(saved.ability_asset_ids);
      setNotice("已保存");
      await load();
    } catch (cause) {
      setError(cause instanceof ApiError && cause.status === 409 ? "名字已存在或内容已被其他窗口修改，请重新载入。" : cause instanceof Error ? cause.message : "保存失败");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (component: Component) => {
    if (!window.confirm(`确认删除「${component.name}」？`)) return;
    setBusy(true);
    setError("");
    try {
      await api(`/creator/${component.kind === "ability" ? "abilities" : "characters"}/${component.id}`, { method: "DELETE" });
      if (editing?.id === component.id) setEditing(null);
      await load();
      setNotice("已删除");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "删除失败");
    } finally {
      setBusy(false);
    }
  };

  const toggleAbility = (abilityId: string) => {
    setEquipped((current) => current.includes(abilityId)
      ? current.filter((id) => id !== abilityId)
      : current.length >= 4 ? current : [...current, abilityId]);
  };

  const actions = (component: Component) => <div className="creator-entry__actions">
    <button className="btn btn-ghost btn-icon" title="编辑" aria-label={`编辑 ${component.name}`} disabled={busy} onClick={() => openEditor(component)}><PencilIcon size={15} /></button>
    <button className="btn btn-danger btn-icon" title="删除" aria-label={`删除 ${component.name}`} disabled={busy} onClick={() => void remove(component)}><TrashIcon size={15} /></button>
  </div>;

  const characterEntry = (component: Component, index: number) => {
    const equippedNames = component.ability_asset_ids.map((id) => abilityNames.get(id) ?? "已删除奇术");
    return <article className="creator-character-card" key={component.id}>
      <div className="creator-character-card__head">
        <h3><span className="seal">{index + 1}</span>{component.name}</h3>
        <span className="creator-character-card__count">{equippedNames.length} 门奇术</span>
      </div>
      <ShortText value={component.content.bio || "暂无角色介绍"} className="creator-character-card__bio" />
      <div className="creator-character-card__chips" aria-label="已装配奇术">
        {equippedNames.length ? equippedNames.map((name, abilityIndex) => <span className="chip chip--ability" key={`${component.id}-${abilityIndex}`}>{name}</span>) : <span className="creator-character-card__empty">尚未装配奇术</span>}
      </div>
      <div className="creator-character-card__foot">
        <span>私有条目</span>
        {actions(component)}
      </div>
    </article>;
  };

  const abilityEntry = (component: Component) => <article className="creator-ability-card" key={component.id}>
    <div className="creator-ability-card__head">
      <h3>{component.name}</h3>
      {actions(component)}
    </div>
    <p className="creator-ability-card__effect">{component.content.effect || "待填写效果"}</p>
    <ShortText value={component.content.detail || "暂无详述"} className="creator-ability-card__detail" />
  </article>;

  const field = (label: string, key: string, max: number, rows = 1) => <label className="field"><span>{label}<small>{(draft[key] ?? "").length}/{max}</small></span>{rows > 1 ? <textarea className="textarea" rows={rows} maxLength={max} disabled={busy} value={draft[key] ?? ""} onChange={(event) => setDraft({ ...draft, [key]: event.target.value })} /> : <input className="input" maxLength={max} disabled={busy} value={draft[key] ?? ""} onChange={(event) => setDraft({ ...draft, [key]: event.target.value })} />}</label>;

  if (editing) {
    const isAbility = editing.kind === "ability";
    return <section className="creator-studio creator-editor"><header className="creator-hero"><div><h1>编辑{isAbility ? "奇术" : "奇人"}</h1><p>保存后立即更新自己的私有组件。</p></div><button className="btn btn-ghost" disabled={busy} onClick={() => { setEditing(null); setError(""); }}>返回异闻录</button></header>{(error || notice) && <p className={error ? "creator-alert" : "creator-notice"}>{error || notice}</p>}<div className="creator-editor__sheet"><div className="creator-form">{isAbility ? <>{field("名字", "name", 10)}{field("效果", "effect", 50, 3)}{field("详述", "detail", 500, 5)}</> : <>{field("名字", "name", 30)}{field("角色介绍", "bio", 500, 6)}<fieldset className="creator-equipment"><legend>装配奇术 <small>{equipped.length}/4</small></legend>{abilities.length ? <div className="creator-equipment__list">{abilities.map((ability) => <label key={ability.id}><input type="checkbox" checked={equipped.includes(ability.id)} disabled={busy || (!equipped.includes(ability.id) && equipped.length >= 4)} onChange={() => toggleAbility(ability.id)} /><span><b>{ability.name}</b><small>{ability.content.effect}</small></span></label>)}</div> : <p className="muted">尚未创建奇术，先返回异闻录新建一门奇术。</p>}</fieldset></>}</div><div className="creator-canvas__actions"><button className="btn btn-primary" disabled={busy} onClick={() => void save()}>保存</button><button className="btn btn-danger" disabled={busy} onClick={() => void remove(editing)}><TrashIcon size={14} /> 删除</button></div></div></section>;
  }

  const isCharacterTab = activeKind === "character";
  const items = isCharacterTab ? characters : abilities;
  return <section className="creator-studio creator-codex"><header className="creator-hero"><div><h1>异闻录</h1><p>收录自己的奇人、奇术，并为小天下集准备可用阵容。</p></div><Link className="btn btn-ghost" to="/scenarios">浏览小天下集</Link></header>{(error || notice) && <p className={error ? "creator-alert" : "creator-notice"}>{error || notice}</p>}<div className="creator-tabs-native" role="tablist" aria-label="异闻录篇章"><button type="button" role="tab" aria-selected={isCharacterTab} className={isCharacterTab ? "is-active" : ""} onClick={() => setActiveKind("character")}>奇人篇<span>{characters.length}</span></button><button type="button" role="tab" aria-selected={!isCharacterTab} className={!isCharacterTab ? "is-active" : ""} onClick={() => setActiveKind("ability")}>奇术篇<span>{abilities.length}</span></button></div><section className="creator-chapter" aria-label={isCharacterTab ? "奇人篇" : "奇术篇"}><header className="creator-chapter__head"><div><h2>{isCharacterTab ? "奇人篇" : "奇术篇"}</h2><p>{isCharacterTab ? "角色介绍与已装配的奇术" : "奇术效果与详述"}</p></div><button className="btn btn-primary" disabled={busy} onClick={() => void create(activeKind)}><PlusIcon size={15} /> 新建{isCharacterTab ? "奇人" : "奇术"}</button></header><div className={isCharacterTab ? "creator-character-grid" : "creator-ability-grid"}>{items.length ? isCharacterTab ? characters.map(characterEntry) : abilities.map(abilityEntry) : <div className="empty creator-chapter__empty">尚未收录{isCharacterTab ? "奇人" : "奇术"}</div>}</div></section></section>;
}
