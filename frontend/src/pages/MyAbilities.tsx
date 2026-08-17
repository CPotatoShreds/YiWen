import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api } from "../api";
import type { Ability, Loadout } from "../types";
import { LOADOUT_NUMBERS, loadoutLabel, parseUnderstanding } from "../types";
import { CheckIcon, PencilIcon, PlusIcon, ScrollIcon, TrashIcon, XIcon } from "../components/icons";

const MAX_SLOTS = 4; // 每位奇人最多装配 4 个奇术

// 三相因果槽位的展示配置（与后端 Phase 对应）
const PHASE_LABELS: { key: "pre" | "mid" | "post"; label: string }[] = [
  { key: "pre", label: "契相" },
  { key: "mid", label: "显相" },
  { key: "post", label: "果相" },
];

// 字段字数上限（与后端 AbilitySetIn 的 max_length 对齐）
const FIELD_LIMITS = { name: 10, effect: 50, detail: 500 };

// 三相理论简介（弹窗问号悬浮提示，与 services/ability_understanding.py 的三相提示词同源）
// 契相/显相/果相 等专有名词主题红；「至少一相」主题红加粗
function ThreePhaseTheory() {
  return (
    <>
      三相理论：任何奇术都须在「<em className="tip-help__term">契相</em>」「<em className="tip-help__term">显相</em>」「<em className="tip-help__term">果相</em>」<strong className="tip-help__term">至少一相</strong>与世界共鸣，才能使其蕴含的力量降临；共鸣「相」的数量越多，「相」本身的效果越好，奇术的效果就越强。若三相皆无，奇术效果将被削弱至近乎为零。
      <br />
      「<em className="tip-help__term">契相</em>」：启动前置。发动前须向世界支付的仪式、动作、时间与交互让渡。
      <br />
      「<em className="tip-help__term">显相</em>」：运作机制。能力如何干涉现实、令其生效的过程与机理解释。
      <br />
      「<em className="tip-help__term">果相</em>」：代价反噬。结算后的系统负债、自损与对等规则。
    </>
  );
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
  detail,
  busy,
  onChange,
  onSave,
  onClose,
}: {
  editing: Ability | null;
  name: string;
  effect: string;
  detail: string;
  busy: boolean;
  onChange: (p: { name?: string; effect?: string; detail?: string }) => void;
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

  const over =
    name.length > FIELD_LIMITS.name ||
    effect.length > FIELD_LIMITS.effect ||
    detail.length > FIELD_LIMITS.detail;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="modal__head">
          <h3>{editing ? `修订「${editing.name}」` : "新增奇术"}</h3>
          <button className="modal__close" onClick={onClose} aria-label="关闭">
            <XIcon size={16} />
          </button>
        </div>
        <p className="muted" style={{ padding: "0 2px 14px", lineHeight: 1.7 }}>
          奇术写下后，AI 会基于三相理论对其进行解析
          <span className="tip tip-help" tabIndex={0}>
            <span className="tip-help__mark">?</span>
            <span className="tip__bubble"><ThreePhaseTheory /></span>
          </span>
        </p>
        <div className="field">
          <label htmlFor="ab-name">名目</label>
          <span className={`char-count${name.length > FIELD_LIMITS.name ? " char-count--over" : ""}`}>
            {name.length}/{FIELD_LIMITS.name}
          </span>
          <input
            id="ab-name"
            className="input"
            value={name}
            maxLength={FIELD_LIMITS.name}
            onChange={(e) => onChange({ name: e.target.value })}
            autoFocus
          />
        </div>
        <div className="field">
          <label htmlFor="ab-effect">效果</label>
          <span className={`char-count${effect.length > FIELD_LIMITS.effect ? " char-count--over" : ""}`}>
            {effect.length}/{FIELD_LIMITS.effect}
          </span>
          <textarea
            id="ab-effect"
            className="textarea"
            value={effect}
            maxLength={FIELD_LIMITS.effect}
            onChange={(e) => onChange({ effect: e.target.value })}
            rows={4}
          />
        </div>
        <div className="field">
          <label htmlFor="ab-detail">详细阐述</label>
          <span className={`char-count${detail.length > FIELD_LIMITS.detail ? " char-count--over" : ""}`}>
            {detail.length}/{FIELD_LIMITS.detail}
          </span>
          <textarea
            id="ab-detail"
            className="textarea"
            value={detail}
            maxLength={FIELD_LIMITS.detail}
            onChange={(e) => onChange({ detail: e.target.value })}
            placeholder="在此处进一步阐述奇术的限制、具体实现方式、代价以及其他的效果细节；阐述内容越详细，AI 理解越准确；如果 AI 的三相解析与您预期不符，也可于此处添加适当解释，帮助 AI 理解"
            rows={4}
          />
        </div>
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button className="btn btn-ghost" onClick={onClose}>
            作罢
          </button>
          <button className="btn btn-primary" onClick={onSave} disabled={busy || over || !name.trim() || !effect.trim()}>
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

// 两步向导：第 1 步从奇术库勾选 1-4 门，第 2 步填姓名/角色介绍/战术
function CreateLoadoutWizard({
  step,
  picked,
  pool,
  busy,
  name,
  style,
  tactic,
  err,
  onToggle,
  onNext,
  onBack,
  onChange,
  onSave,
  onClose,
}: {
  step: 1 | 2;
  picked: Set<string>;
  pool: Ability[];
  busy: boolean;
  name: string;
  style: string;
  tactic: string;
  err: string;
  onToggle: (id: string) => void;
  onNext: () => void;
  onBack: () => void;
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
      <div className="modal picker-modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
        <div className="modal__head">
          <h3>{step === 1 ? "新增奇人 · 选奇术" : "新增奇人 · 立名目"}</h3>
          <button className="modal__close" onClick={onClose} aria-label="关闭">
            <XIcon size={16} />
          </button>
        </div>
        {step === 1 ? (
          <>
            <p className="muted" style={{ padding: "2px 2px 12px" }}>
              第 1 步：从奇术库勾选 1-4 门奇术，点「生成 →」。
            </p>
            {pool.length === 0 ? (
              <p className="muted" style={{ padding: "8px 2px 14px" }}>
                奇术篇是空的。先去写下奇术，再来立起奇人。
              </p>
            ) : (
              <div className="picker">
                {pool.map((a) => {
                  const sel = picked.has(a.id);
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
              已选 {picked.size} / 最多 {MAX_SLOTS}
            </div>
            <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
              <button className="btn btn-ghost" onClick={onClose}>
                作罢
              </button>
              <button className="btn btn-primary" onClick={onNext} disabled={picked.size === 0}>
                <ScrollIcon size={15} />
                生成 →
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="field">
              <label htmlFor="wz-name">姓名</label>
              <input
                id="wz-name"
                className="input"
                value={name}
                onChange={(e) => onChange({ name: e.target.value })}
                autoFocus
              />
            </div>
            <div className="field">
              <label htmlFor="wz-style">角色介绍</label>
              <input
                id="wz-style"
                className="input"
                value={style}
                onChange={(e) => onChange({ style: e.target.value })}
                placeholder="可选，角色相关信息，如性格特征、个人习惯、行事风格等"
              />
            </div>
            <div className="field">
              <label htmlFor="wz-tactic">战术</label>
              <textarea
                id="wz-tactic"
                className="textarea"
                value={tactic}
                onChange={(e) => onChange({ tactic: e.target.value })}
                placeholder="可于此处基于角色拥有的奇术制定战术，推演战斗时，角色会依据战术指导行动"
                rows={3}
              />
            </div>
            {err && <p className="err" style={{ margin: "4px 2px 0" }}>{err}</p>}
            <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
              <button className="btn btn-ghost" onClick={onBack}>
                上一步
              </button>
              <button className="btn btn-primary" onClick={onSave} disabled={busy || !name.trim()}>
                <PlusIcon size={15} />
                {busy ? "写入中…" : "立起奇人"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// 编辑奇人（姓名 / 角色介绍 / 战术）：点击卡上「编辑」按钮后悬浮修改
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
          <label htmlFor="e-ld-style">角色介绍</label>
          <input
            id="e-ld-style"
            className="input"
            value={style}
            onChange={(e) => onChange({ style: e.target.value })}
            placeholder="可选，角色相关信息，如性格特征、个人习惯、行事风格等"
          />
        </div>
        <div className="field">
          <label htmlFor="e-ld-tactic">战术</label>
          <textarea
            id="e-ld-tactic"
            className="textarea"
            value={tactic}
            onChange={(e) => onChange({ tactic: e.target.value })}
            placeholder="可于此处基于角色拥有的奇术制定战术，推演战斗时，角色会依据战术指导行动"
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
  const [detail, setDetail] = useState("");
  const [busy, setBusy] = useState(false);
  const [awaiting, setAwaiting] = useState<Set<string>>(new Set()); // 刚保存、槽位尚在后台生成的奇术 id

  // 新增奇人（两步向导）
  const [charModal, setCharModal] = useState(false);
  const [charStep, setCharStep] = useState<1 | 2>(1);
  const [charName, setCharName] = useState("");
  const [charStyle, setCharStyle] = useState("");
  const [charTactic, setCharTactic] = useState("");
  const [charPicked, setCharPicked] = useState<Set<string>>(new Set());
  const [charErr, setCharErr] = useState("");

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
    setDetail("");
    setModal(true);
  }
  function openEdit(a: Ability) {
    setEditing(a);
    setName(a.name);
    setEffect(a.effect);
    setDetail(a.detail ?? "");
    setModal(true);
  }

  async function save() {
    setBusy(true);
    setErr("");
    try {
      const body = JSON.stringify({ name: name.trim(), effect: effect.trim(), detail: detail.trim() });
      const saved = editing
        ? await api<Ability>(`/abilities/${editing.id}`, { method: "PUT", body })
        : await api<Ability>("/abilities", { method: "POST", body });
      setModal(false);
      await load();
      // 槽位在后台异步生成：短轮询直到出现或超时（带 ?t= 绕过 SWR 缓存）
      setAwaiting((s) => new Set(s).add(saved.id));
      void pollSlot(saved.id);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  // 保存后轮询 /abilities/mine，槽位出现即停止；最多 6 次、每 2.5s 一次
  async function pollSlot(id: string) {
    for (let i = 0; i < 6; i++) {
      await new Promise((r) => setTimeout(r, 2500));
      try {
        const fresh = await api<Ability[]>(`/abilities/mine?t=${Date.now()}`);
        setList(fresh);
        if (fresh.find((x) => x.id === id)?.understanding) break;
      } catch {
        // 单次失败静默，下一轮再试
      }
    }
    setAwaiting((s) => {
      const next = new Set(s);
      next.delete(id);
      return next;
    });
  }

  function openCreateChar() {
    setCharStep(1);
    setCharName("");
    setCharStyle("");
    setCharTactic("");
    setCharPicked(new Set());
    setCharErr("");
    setCharModal(true);
  }
  function toggleCharPicked(id: string) {
    setCharErr("");
    if (charPicked.has(id)) {
      const next = new Set(charPicked);
      next.delete(id);
      setCharPicked(next);
      return;
    }
    if (charPicked.size >= MAX_SLOTS) {
      setCharErr(`每位奇人最多装配 ${MAX_SLOTS} 个奇术，已满。`);
      return;
    }
    const next = new Set(charPicked);
    next.add(id);
    setCharPicked(next);
  }

  async function createCharacter() {
    setBusy(true);
    setCharErr("");
    try {
      await api("/loadouts", {
        method: "POST",
        body: JSON.stringify({
          name: charName.trim(),
          style: charStyle.trim(),
          tactic: charTactic.trim(),
          ability_ids: [...charPicked],
        }),
      });
      setCharModal(false);
      await load(); // 立起后横向列表已含新奇人
    } catch (e: any) {
      setCharErr(e.message);
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

      {/* 奇人篇：响应式网格扁平卡 */}
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
          <p>立起第一位奇人——先勾选 1-4 门奇术，再填姓名与角色介绍，解封即可启程。</p>
          <button className="btn btn-primary" onClick={openCreateChar}>
            <PlusIcon size={15} />
            立起第一位奇人
          </button>
        </div>
      ) : (
        <div className="char-grid">
          {loadouts.map((l, i) => (
            <div className={`char-card char-card--manage${l.enabled ? " is-on" : ""}`} key={l.id}>
              <div className="char-card__head">
                <span className="char-card__name">
                  <span className="seal">{LOADOUT_NUMBERS[i] ?? i + 1}</span>
                  {loadoutLabel(l, i)}
                </span>
                <label className="toggle" title={l.enabled ? "点击未解封" : "点击解封"}>
                  <input
                    type="checkbox"
                    checked={l.enabled}
                    onChange={(e) => setEnabled(l, e.target.checked)}
                  />
                  <span className="toggle__track" />
                </label>
              </div>
              {l.style && (
                <p className="muted" style={{ fontSize: 12, margin: "6px 0 0" }}>
                  {l.style}
                </p>
              )}

              <div className="char-card__slots">
                {Array.from({ length: MAX_SLOTS }, (_, j) => {
                  const a = l.abilities[j];
                  if (a) {
                    return (
                      <Tip key={a.id} label={`${a.name}：${a.effect}`}>
                        <span className="char-card__slot char-card__slot--on">
                          <span className="char-card__slot-name">{a.name}</span>
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
                    );
                  }
                  return (
                    <button
                      className="char-card__slot char-card__slot--empty"
                      key={`empty-${j}`}
                      onClick={() => openPicker(l)}
                      title="装入奇术"
                    >
                      <PlusIcon size={12} />
                      空位
                    </button>
                  );
                })}
              </div>

              <div className="char-card__foot">
                <button className="btn btn-ghost btn-sm" onClick={() => openEditLd(l)}>
                  <PencilIcon size={14} />
                  编辑
                </button>
                <button
                  className="btn btn-danger btn-sm"
                  onClick={() => setConfirm({ kind: "loadout", id: l.id, name: loadoutLabel(l, i) })}
                >
                  <TrashIcon size={14} />
                  删除
                </button>
              </div>
            </div>
          ))}

          <button
            className="char-card char-card--add"
            onClick={openCreateChar}
            disabled={loadouts.length >= maxLoadouts}
            title={
              loadouts.length >= maxLoadouts
                ? `见闻不足，未能解锁更多奇人槽位（${maxLoadouts}/${maxLoadouts}）`
                : undefined
            }
          >
            <PlusIcon size={22} />
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
          <p>点击右上角「新增奇术」，写下第一招奇术的名目、效果与详细解释，再装入奇人解封。</p>
        </div>
      ) : (
        list.map((a) => {
          const chars = loadouts
            .map((l, i) => (l.abilities.some((x) => x.id === a.id) ? i : -1))
            .filter((n) => n >= 0);
          const slot = parseUnderstanding(a.understanding);
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
                {a.detail && <p className="ability-item__detail">{a.detail}</p>}
                {awaiting.has(a.id) && !slot ? (
                  <p className="ability-item__pending">因果解析生成中…</p>
                ) : null}
                {slot && (slot.verdict.zero_phase || PHASE_LABELS.some(({ key }) => slot[key].present)) && (
                  <div className="ability-slot">
                    {slot.verdict.zero_phase && (
                      <div className="ability-slot__zero">
                        <span className="ability-slot__zero-pill">三相皆无</span>
                        <span className="ability-slot__zero-note">奇术效果被削弱至近乎为零</span>
                      </div>
                    )}
                    {PHASE_LABELS.map(({ key, label }) => {
                      const ph = slot[key];
                      if (!ph.present) return null;
                      return (
                        <div className="ability-slot__phase" key={key}>
                          <span className="ability-slot__phase-label">{label}</span>
                          <span className="ability-slot__phase-text">{ph.text}</span>
                        </div>
                      );
                    })}
                  </div>
                )}
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
          detail={detail}
          busy={busy}
          onChange={(p) => {
            if (p.name !== undefined) setName(p.name);
            if (p.effect !== undefined) setEffect(p.effect);
            if (p.detail !== undefined) setDetail(p.detail);
          }}
          onSave={save}
          onClose={() => setModal(false)}
        />
      )}
      {charModal && (
        <CreateLoadoutWizard
          step={charStep}
          picked={charPicked}
          pool={list}
          busy={busy}
          name={charName}
          style={charStyle}
          tactic={charTactic}
          err={charErr}
          onToggle={toggleCharPicked}
          onNext={() => setCharStep(2)}
          onBack={() => setCharStep(1)}
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
