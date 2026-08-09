import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { api } from "../api";
import { CheckIcon, PencilIcon, PlusIcon, TrashIcon, XIcon } from "../components/icons";

interface Ability {
  id: string;
  name: string;
  effect: string;
}
interface Loadout {
  id: number;
  name: string;
  style: string;
  enabled: boolean;
  tactic: string;
  abilities: Ability[];
}

const NUM = ["壹", "贰", "叁", "肆", "伍", "陆", "柒", "捌", "玖", "拾"];
const MAX_SLOTS = 4; // 每位奇人最多装配 4 个奇术

// 奇人展示名：有姓名用姓名，否则占位「奇人·壹/贰/…/拾」
function loadoutLabel(l: Loadout, i: number): string {
  return l.name || `奇人·${NUM[i] ?? i + 1}`;
}

// 奇术信息悬浮提示：鼠标悬浮显示名目与效果
function Tip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <span className="tip">
      {children}
      <span className="tip__bubble">{label}</span>
    </span>
  );
}

function AbilityModal({
  editing,
  name,
  effect,
  busy,
  onChange,
  onSave,
  onClose,
}: {
  editing: Ability | null;
  name: string;
  effect: string;
  busy: boolean;
  onChange: (p: { name?: string; effect?: string }) => void;
  onSave: () => void;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="modal__head">
          <h3>{editing ? `修订「${editing.name}」` : "新增奇术"}</h3>
          <button className="modal__close" onClick={onClose} aria-label="关闭">
            <XIcon size={16} />
          </button>
        </div>
        <div className="field">
          <label htmlFor="ab-name">名目</label>
          <input
            id="ab-name"
            className="input"
            value={name}
            onChange={(e) => onChange({ name: e.target.value })}
            placeholder="如：燃烬之握"
            autoFocus
          />
        </div>
        <div className="field">
          <label htmlFor="ab-effect">效果</label>
          <textarea
            id="ab-effect"
            className="textarea"
            value={effect}
            onChange={(e) => onChange({ effect: e.target.value })}
            placeholder="如：接触的物体被点燃为不会熄灭的火焰，火焰温度随心念升降"
            rows={4}
          />
        </div>
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button className="btn btn-ghost" onClick={onClose}>
            作罢
          </button>
          <button className="btn btn-primary" onClick={onSave} disabled={busy || !name.trim() || !effect.trim()}>
            <PlusIcon size={15} />
            {busy ? "写入中…" : editing ? "存下修订" : "写下奇术"}
          </button>
        </div>
      </div>
    </div>
  );
}

function ConfirmDialog({
  title,
  text,
  busy,
  onConfirm,
  onClose,
}: {
  title: string;
  text: string;
  busy: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="modal__head">
          <h3>{title}</h3>
          <button className="modal__close" onClick={onClose} aria-label="关闭">
            <XIcon size={16} />
          </button>
        </div>
        <p className="muted" style={{ padding: "2px 2px 14px", lineHeight: 1.7 }}>
          {text}
        </p>
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button className="btn btn-ghost" onClick={onClose}>
            作罢
          </button>
          <button className="btn btn-danger" onClick={onConfirm} disabled={busy}>
            <TrashIcon size={15} />
            {busy ? "删除中…" : "确认删除"}
          </button>
        </div>
      </div>
    </div>
  );
}

function CharacterModal({
  busy,
  name,
  style,
  tactic,
  onChange,
  onSave,
  onClose,
}: {
  busy: boolean;
  name: string;
  style: string;
  tactic: string;
  onChange: (p: { name?: string; style?: string; tactic?: string }) => void;
  onSave: () => void;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="modal__head">
          <h3>新增奇人</h3>
          <button className="modal__close" onClick={onClose} aria-label="关闭">
            <XIcon size={16} />
          </button>
        </div>
        <div className="field">
          <label htmlFor="ld-name">姓名</label>
          <input
            id="ld-name"
            className="input"
            value={name}
            onChange={(e) => onChange({ name: e.target.value })}
            placeholder="如：白鹤仙人"
            autoFocus
          />
        </div>
        <div className="field">
          <label htmlFor="ld-style">战斗风格</label>
          <input
            id="ld-style"
            className="input"
            value={style}
            onChange={(e) => onChange({ style: e.target.value })}
            placeholder="可选，如：轻功卓绝，来去无踪"
          />
        </div>
        <div className="field">
          <label htmlFor="ld-tactic">战术</label>
          <textarea
            id="ld-tactic"
            className="textarea"
            value={tactic}
            onChange={(e) => onChange({ tactic: e.target.value })}
            placeholder="这位奇人该怎么打…（可选）"
            rows={3}
          />
        </div>
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button className="btn btn-ghost" onClick={onClose}>
            作罢
          </button>
          <button className="btn btn-primary" onClick={onSave} disabled={busy || !name.trim()}>
            <PlusIcon size={15} />
            {busy ? "写入中…" : "立起奇人"}
          </button>
        </div>
      </div>
    </div>
  );
}

// 编辑奇人（姓名 / 战斗风格 / 战术）：点击卡上「编辑」按钮后悬浮修改
function EditLoadoutModal({
  busy,
  name,
  style,
  tactic,
  onChange,
  onSave,
  onClose,
}: {
  busy: boolean;
  name: string;
  style: string;
  tactic: string;
  onChange: (p: { name?: string; style?: string; tactic?: string }) => void;
  onSave: () => void;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="modal__head">
          <h3>编辑奇人</h3>
          <button className="modal__close" onClick={onClose} aria-label="关闭">
            <XIcon size={16} />
          </button>
        </div>
        <div className="field">
          <label htmlFor="e-ld-name">姓名</label>
          <input
            id="e-ld-name"
            className="input"
            value={name}
            onChange={(e) => onChange({ name: e.target.value })}
            autoFocus
          />
        </div>
        <div className="field">
          <label htmlFor="e-ld-style">战斗风格</label>
          <input
            id="e-ld-style"
            className="input"
            value={style}
            onChange={(e) => onChange({ style: e.target.value })}
            placeholder="可选，如：轻功卓绝，来去无踪"
          />
        </div>
        <div className="field">
          <label htmlFor="e-ld-tactic">战术</label>
          <textarea
            id="e-ld-tactic"
            className="textarea"
            value={tactic}
            onChange={(e) => onChange({ tactic: e.target.value })}
            placeholder="这位奇人该怎么打…（可选）"
            rows={3}
          />
        </div>
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button className="btn btn-ghost" onClick={onClose}>
            作罢
          </button>
          <button className="btn btn-primary" onClick={onSave} disabled={busy}>
            <CheckIcon size={15} />
            {busy ? "保存中…" : "存下"}
          </button>
        </div>
      </div>
    </div>
  );
}

// 奇术多选悬浮窗：加号点开，按钮式奇术逐个悬浮看信息，可多选，超过 4 个提醒
function AbilityPicker({
  loadout,
  pool,
  selected,
  maxAdd,
  busy,
  err,
  onToggle,
  onApply,
  onClose,
}: {
  loadout: Loadout;
  pool: Ability[];
  selected: Set<string>;
  maxAdd: number;
  busy: boolean;
  err: string;
  onToggle: (id: string) => void;
  onApply: () => void;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal picker-modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="modal__head">
          <h3>给「{loadout.name || "这位奇人"}」装入奇术</h3>
          <button className="modal__close" onClick={onClose} aria-label="关闭">
            <XIcon size={16} />
          </button>
        </div>
        {pool.length === 0 ? (
          <p className="muted" style={{ padding: "8px 2px 14px" }}>
            奇术篇是空的，或所有奇术都已装入。先去写下新奇术吧。
          </p>
        ) : (
          <div className="picker">
            {pool.map((a) => {
              const sel = selected.has(a.id);
              return (
                <Tip key={a.id} label={`${a.name}：${a.effect}`}>
                  <button className={`picker-item${sel ? " is-on" : ""}`} onClick={() => onToggle(a.id)}>
                    <span className="picker-item__name">{a.name}</span>
                    <span className="picker-item__eff">{a.effect}</span>
                    {sel && (
                      <span className="picker-item__check">
                        <CheckIcon size={16} />
                      </span>
                    )}
                  </button>
                </Tip>
              );
            })}
          </div>
        )}
        {err && <p className="err" style={{ margin: "4px 2px 0" }}>{err}</p>}
        <div className="poker__count" style={{ marginTop: 8 }}>
          已选 {selected.size} / 可再装 {Math.max(0, maxAdd)}
        </div>
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button className="btn btn-ghost" onClick={onClose}>
            取消
          </button>
          <button className="btn btn-primary" onClick={onApply} disabled={busy || selected.size === 0}>
            <CheckIcon size={15} />
            {busy ? "装配中…" : `装配 ${selected.size > 0 ? selected.size : ""}`.trim()}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function MyAbilities() {
  const [list, setList] = useState<Ability[]>([]);
  const [loadouts, setLoadouts] = useState<Loadout[]>([]);
  const [maxLoadouts, setMaxLoadouts] = useState(3); // 按见闻解锁的奇人槽位上限（/auth/me 现拉）
  const [ready, setReady] = useState(false); // 首次加载完成前显示骨架，避免把空态误判为加载中
  const [err, setErr] = useState("");

  // 奇术 CRUD（奇术篇）
  const [modal, setModal] = useState(false);
  const [editing, setEditing] = useState<Ability | null>(null);
  const [name, setName] = useState("");
  const [effect, setEffect] = useState("");
  const [busy, setBusy] = useState(false);

  // 新增奇人
  const [charModal, setCharModal] = useState(false);
  const [charName, setCharName] = useState("");
  const [charStyle, setCharStyle] = useState("");
  const [charTactic, setCharTactic] = useState("");

  // 编辑奇人（悬浮窗）
  const [editLd, setEditLd] = useState<Loadout | null>(null);
  const [editName, setEditName] = useState("");
  const [editStyle, setEditStyle] = useState("");
  const [editTactic, setEditTactic] = useState("");

  // 加号多选装配（悬浮窗）
  const [pickerLd, setPickerLd] = useState<Loadout | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [pickerErr, setPickerErr] = useState("");

  // 删除确认（奇术/奇人通用）
  const [confirm, setConfirm] = useState<{ kind: "ability" | "loadout"; id: string | number; name: string } | null>(null);
  const [deleting, setDeleting] = useState(false);

  async function load() {
    try {
      const [abilList, lds, me] = await Promise.all([
        api<Ability[]>("/abilities/mine"),
        api<Loadout[]>("/loadouts"),
        api<{ max_loadouts: number }>("/auth/me"),
      ]);
      setList(abilList);
      setLoadouts(lds);
      setMaxLoadouts(me.max_loadouts);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setReady(true);
    }
  }
  useEffect(() => {
    load();
  }, []);

  function openCreate() {
    setEditing(null);
    setName("");
    setEffect("");
    setModal(true);
  }
  function openEdit(a: Ability) {
    setEditing(a);
    setName(a.name);
    setEffect(a.effect);
    setModal(true);
  }

  async function save() {
    setBusy(true);
    setErr("");
    try {
      if (editing) {
        await api(`/abilities/${editing.id}`, {
          method: "PUT",
          body: JSON.stringify({ name: name.trim(), effect: effect.trim() }),
        });
      } else {
        await api("/abilities", {
          method: "POST",
          body: JSON.stringify({ name: name.trim(), effect: effect.trim() }),
        });
      }
      setModal(false);
      await load();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function createCharacter() {
    setBusy(true);
    setErr("");
    try {
      await api("/loadouts", {
        method: "POST",
        body: JSON.stringify({
          name: charName.trim(),
          style: charStyle.trim(),
          tactic: charTactic.trim(),
        }),
      });
      setCharModal(false);
      await load(); // 立起后横向列表已含新奇人
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function doDelete() {
    if (!confirm) return;
    setDeleting(true);
    setErr("");
    try {
      await api(`/${confirm.kind === "ability" ? "abilities" : "loadouts"}/${confirm.id}`, { method: "DELETE" });
      setConfirm(null);
      await load();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setDeleting(false);
    }
  }

  async function setEnabled(l: Loadout, value: boolean) {
    if (value && l.abilities.length === 0) {
      setErr("这位奇人尚无奇术，至少装入一个才能解封。");
      return;
    }
    setErr("");
    try {
      await api(`/loadouts/${l.id}`, { method: "PUT", body: JSON.stringify({ enabled: value }) });
      await load();
    } catch (e: any) {
      setErr(e.message);
    }
  }


  // 编辑悬浮窗：打开时填入当前值
  function openEditLd(l: Loadout) {
    setEditLd(l);
    setEditName(l.name ?? "");
    setEditStyle(l.style ?? "");
    setEditTactic(l.tactic ?? "");
  }
  async function saveEdit() {
    if (!editLd) return;
    setBusy(true);
    setErr("");
    try {
      await api(`/loadouts/${editLd.id}`, {
        method: "PUT",
        body: JSON.stringify({ name: editName.trim(), style: editStyle.trim(), tactic: editTactic.trim() }),
      });
      setEditLd(null);
      await load();
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  // 加号多选：池 = 未装入的奇术；上限 4，复选超限提醒
  function openPicker(l: Loadout) {
    setPickerLd(l);
    setPicked(new Set());
    setPickerErr("");
  }
  function togglePicked(id: string) {
    if (!pickerLd) return;
    setPickerErr("");
    if (picked.has(id)) {
      const next = new Set(picked);
      next.delete(id);
      setPicked(next);
      return;
    }
    const maxAdd = Math.max(0, MAX_SLOTS - pickerLd.abilities.length);
    if (picked.size >= maxAdd) {
      setPickerErr(`每位奇人最多装配 ${MAX_SLOTS} 个奇术，已满。`);
      return;
    }
    const next = new Set(picked);
    next.add(id);
    setPicked(next);
  }
  async function applyPicker() {
    if (!pickerLd) return;
    setBusy(true);
    setPickerErr("");
    try {
      for (const id of picked) {
        await api(`/loadouts/${pickerLd.id}/abilities/${id}`, { method: "POST" });
      }
      setPickerLd(null);
      await load();
    } catch (e: any) {
      setPickerErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function removeAbility(l: Loadout, abilityId: string) {
    try {
      await api(`/loadouts/${l.id}/abilities/${abilityId}`, { method: "DELETE" });
      await load();
    } catch (e: any) {
      setErr(e.message);
    }
  }

  // 横向列表拖动：鼠标 Pointer Events 手拖滚动（触屏走浏览器原生滚动，不接管）。
  // 不用 setPointerCapture——它会把 click 重定向到 rail，让卡内按钮/登台开关收不到点击；
  // 鼠标指针按下时本就隐式捕获，move/up 事件会冒泡回 rail。拖动超 5px 视为滚动，
  // 用 suppress 标记吞掉随之而来的那一次 click，避免误触卡内控件。
  const railRef = useRef<HTMLDivElement>(null);
  const drag = useRef({ startX: 0, startLeft: 0, down: false, moved: false, suppress: false });

  function onRailDown(e: React.PointerEvent<HTMLDivElement>) {
    const el = railRef.current;
    if (!el) return;
    drag.current = { startX: e.clientX, startLeft: el.scrollLeft, down: true, moved: false, suppress: false };
  }
  function onRailMove(e: React.PointerEvent<HTMLDivElement>) {
    const d = drag.current;
    const el = railRef.current;
    if (!d.down || !el || e.pointerType !== "mouse") return;
    const dx = e.clientX - d.startX;
    if (Math.abs(dx) > 5) d.moved = true;
    el.scrollLeft = d.startLeft - dx;
  }
  function onRailUp() {
    const d = drag.current;
    if (d.down && d.moved) d.suppress = true;
    d.down = false;
  }
  function onRailClick(e: React.MouseEvent<HTMLDivElement>) {
    if (drag.current.suppress) {
      drag.current.suppress = false;
      e.preventDefault();
      e.stopPropagation();
    }
  }

  const pool = pickerLd ? list.filter((a) => !pickerLd.abilities.some((x) => x.id === a.id)) : [];

  return (
    <>
      <div className="section-head">
        <h1 className="section-title">异闻录</h1>
        <p className="muted">
          奇术是你笔下自创的招法，奇人是解封的说书角色。奇术装入奇人并解封才会出战，也是对家猜奇术的目标。
        </p>
      </div>
      {err && <p className="err">{err}</p>}

      {/* 奇人篇：横向滚动列表 + 拖动条 */}
      <div className="section-head" style={{ marginTop: 20 }}>
        <h2 className="section-title">
          奇人篇
        </h2>
        <p className="muted">
          每位奇人最多装 {MAX_SLOTS} 个奇术；解封 = 可主动启程，也被他人摇签点名。见闻满 50 解锁 1 个新槽位。
        </p>
      </div>

      {!ready ? (
        <div className="skeleton" style={{ height: 160 }} />
      ) : loadouts.length === 0 ? (
        <div className="empty" style={{ marginTop: 8 }}>
          <PlusIcon size={22} />
          <h3>奇人篇还是空的</h3>
          <p>立起第一位奇人——名字必填，之后装入奇术并解封即可启程。</p>
          <button
            className="btn btn-primary"
            onClick={() => {
              setCharName("");
              setCharStyle("");
              setCharTactic("");
              setCharModal(true);
            }}
          >
            <PlusIcon size={15} />
            立起第一位奇人
          </button>
        </div>
      ) : (
        <div
          className="char-rail"
          ref={railRef}
          onPointerDown={onRailDown}
          onPointerMove={onRailMove}
          onPointerUp={onRailUp}
          onPointerCancel={onRailUp}
          onClickCapture={onRailClick}
        >
          {loadouts.map((l, i) => (
            <div className={`poker${l.enabled ? " is-on" : ""}`} key={l.id}>
              <div className="poker__head">
                <span className="poker__seal">{NUM[i] ?? i + 1}</span>
                <span className="poker__name">{loadoutLabel(l, i)}</span>
                <label className="toggle" title={l.enabled ? "点击未解封" : "点击解封"}>
                  <input
                    type="checkbox"
                    checked={l.enabled}
                    onChange={(e) => setEnabled(l, e.target.checked)}
                  />
                  <span className="toggle__track" />
                </label>
              </div>
              <p className="poker__style">{l.style || "　"}</p>

              <div className="poker__slots">
                {l.abilities.map((a) => (
                  <Tip key={a.id} label={`${a.name}：${a.effect}`}>
                    <span className="poker__chip">
                      {a.name}
                      <button
                        className="chip-x"
                        onClick={() => removeAbility(l, a.id)}
                        aria-label={`卸下 ${a.name}`}
                        title="卸下"
                      >
                        <XIcon size={12} />
                      </button>
                    </span>
                  </Tip>
                ))}
                {Array.from({ length: Math.max(0, MAX_SLOTS - l.abilities.length) }, (_, j) => (
                  <span className="poker__chip-empty" key={`empty-${j}`}>
                    <PlusIcon size={12} />
                    空位（点下方「装入」）
                  </span>
                ))}
              </div>

              <p className="poker__count">
                {l.abilities.length}/{MAX_SLOTS} 奇术
              </p>
              <div className="poker__foot">
                <button className="btn btn-ghost btn-sm" onClick={() => openEditLd(l)}>
                  <PencilIcon size={14} />
                  编辑
                </button>
                <button className="btn btn-primary btn-sm" onClick={() => openPicker(l)}>
                  <PlusIcon size={14} />
                  装入
                </button>
                <button
                  className="btn btn-danger btn-sm btn-icon"
                  onClick={() => setConfirm({ kind: "loadout", id: l.id, name: loadoutLabel(l, i) })}
                  title="删除奇人"
                  aria-label="删除奇人"
                >
                  <TrashIcon size={14} />
                </button>
              </div>
            </div>
          ))}

          <button
            className="poker-add"
            onClick={() => {
              setCharName("");
              setCharStyle("");
              setCharTactic("");
              setCharModal(true);
            }}
            disabled={loadouts.length >= maxLoadouts}
            title={
              loadouts.length >= maxLoadouts
                ? `见闻不足，未能解锁更多奇人槽位（${maxLoadouts}/${maxLoadouts}）`
                : undefined
            }
          >
            <PlusIcon size={20} />
            <span>{loadouts.length >= maxLoadouts ? `槽位已满 ${maxLoadouts}/${maxLoadouts}` : "新增奇人"}</span>
          </button>
        </div>
      )}

      {/* 奇术篇 */}
      <div className="section-head" style={{ marginTop: 40 }}>
        <h2 className="section-title">奇术篇（{list.length}）</h2>
        <p className="muted">自创招法，想写什么就写什么；同一奇术可装入多位奇人</p>
        <button className="btn btn-primary btn-sm" onClick={openCreate}>
          <PlusIcon size={14} />
          新增奇术
        </button>
      </div>
      {list.length === 0 ? (
        <div className="empty" style={{ marginTop: 8 }}>
          <PlusIcon size={22} />
          <h3>奇术篇还是空的</h3>
          <p>点击右上角「新增奇术」，写下第一招奇术的名目与效果，再装入奇人解封。</p>
        </div>
      ) : (
        list.map((a) => {
          const chars = loadouts
            .map((l, i) => (l.abilities.some((x) => x.id === a.id) ? i : -1))
            .filter((n) => n >= 0);
          return (
            <div className="ability-item rise" key={a.id}>
              <div className="ability-item__body">
                <div className="ability-item__name">
                  {a.name}
                  {chars.map((i) => (
                    <span className="chip chip--ability" key={i} style={{ fontSize: 11, padding: "2px 9px" }}>
                      {loadoutLabel(loadouts[i], i)}
                    </span>
                  ))}
                </div>
                <p className="ability-item__effect">{a.effect}</p>
              </div>
              <div className="ability-item__actions">
                <button className="btn btn-ghost btn-sm btn-icon" onClick={() => openEdit(a)} title="修订" aria-label="修订">
                  <PencilIcon size={15} />
                </button>
                <button
                  className="btn btn-danger btn-sm btn-icon"
                  onClick={() => setConfirm({ kind: "ability", id: a.id, name: a.name })}
                  title="删除"
                  aria-label="删除"
                >
                  <TrashIcon size={15} />
                </button>
              </div>
            </div>
          );
        })
      )}

      {modal && (
        <AbilityModal
          editing={editing}
          name={name}
          effect={effect}
          busy={busy}
          onChange={(p) => {
            if (p.name !== undefined) setName(p.name);
            if (p.effect !== undefined) setEffect(p.effect);
          }}
          onSave={save}
          onClose={() => setModal(false)}
        />
      )}
      {charModal && (
        <CharacterModal
          busy={busy}
          name={charName}
          style={charStyle}
          tactic={charTactic}
          onChange={(p) => {
            if (p.name !== undefined) setCharName(p.name);
            if (p.style !== undefined) setCharStyle(p.style);
            if (p.tactic !== undefined) setCharTactic(p.tactic);
          }}
          onSave={createCharacter}
          onClose={() => setCharModal(false)}
        />
      )}
      {editLd && (
        <EditLoadoutModal
          busy={busy}
          name={editName}
          style={editStyle}
          tactic={editTactic}
          onChange={(p) => {
            if (p.name !== undefined) setEditName(p.name);
            if (p.style !== undefined) setEditStyle(p.style);
            if (p.tactic !== undefined) setEditTactic(p.tactic);
          }}
          onSave={saveEdit}
          onClose={() => setEditLd(null)}
        />
      )}
      {pickerLd && (
        <AbilityPicker
          loadout={pickerLd}
          pool={pool}
          selected={picked}
          maxAdd={MAX_SLOTS - pickerLd.abilities.length}
          busy={busy}
          err={pickerErr}
          onToggle={togglePicked}
          onApply={applyPicker}
          onClose={() => setPickerLd(null)}
        />
      )}
      {confirm && (
        <ConfirmDialog
          title={confirm.kind === "ability" ? `删除「${confirm.name}」？` : `删除奇人「${confirm.name}」？`}
          text={
            confirm.kind === "ability"
              ? "该奇术会从你所有奇人的装配中一并移除，删除后不可恢复。"
              : "该奇人连同其奇术装配将被一并删除，删除后不可恢复。"
          }
          busy={deleting}
          onConfirm={doDelete}
          onClose={() => setConfirm(null)}
        />
      )}
    </>
  );
}
