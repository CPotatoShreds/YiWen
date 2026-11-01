import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import PageShell from "../components/PageShell";
import { EmptyScroll } from "../components/Ornaments";

type Scenario = { id: string; slug: string; name: string };
type Character = { id: string; name: string; bio: string; ability_ids: string[] };
type Ability = { id: string; name: string };

/**
 * 立异闻：依托某一卷小天下集，选一位自家奇人守卷并写下给挑战者的指导。
 * 操作区与对战页起笔台同款（scenario-console：选人册 + 落策略的格线纸），卷的
 * slug 由路径参数给出，所以不存在「无卷可依」这一屏——读取失败按错误处理。
 */
export default function ScenarioComposer() {
  const navigate = useNavigate();
  const { slug = "" } = useParams();
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [characters, setCharacters] = useState<Character[] | null>(null);
  const [abilities, setAbilities] = useState<Ability[]>([]);
  const [characterId, setCharacterId] = useState("");
  const [guidance, setGuidance] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [broken, setBroken] = useState(false);

  const backTo = `/scenarios/${encodeURIComponent(slug)}`;

  useEffect(() => {
    let alive = true;
    setBroken(false);
    Promise.all([
      api<Scenario>(`/scenarios/${encodeURIComponent(slug)}`),
      api<Character[]>("/creator/characters"),
      api<Ability[]>("/creator/abilities"),
    ])
      .then(([item, rows, arts]) => {
        if (!alive) return;
        setScenario(item);
        setCharacters(rows);
        setAbilities(arts);
        setError("");
      })
      .catch((cause: Error) => {
        if (!alive) return;
        setBroken(true);
        setError(cause.message);
      });
    return () => { alive = false; };
  }, [slug]);

  const abilityNames = new Map(abilities.map((ability) => [ability.id, ability.name]));
  // 与对战页同款：右缘只露前两门奇术名，其余折成 +N
  const artsOf = (character: Character) => {
    const names = character.ability_ids
      .map((id) => abilityNames.get(id))
      .filter((name): name is string => !!name);
    if (!names.length) return character.ability_ids.length ? `${character.ability_ids.length} 门` : "—";
    const head = names.slice(0, 2).join(" / ");
    return names.length > 2 ? `${head} +${names.length - 2}` : head;
  };

  const create = async () => {
    if (!characterId) { setError("请先选一位守方奇人"); return; }
    // 后端此处只收 UUID（scenario_domain.py:310），slug 仅用于读取，不可混用
    if (!scenario?.id) { setError("卷尚未载入，请稍候"); return; }
    setBusy(true);
    setError("");
    try {
      await api(`/creator/scenarios/${scenario.id}/rosters`, { method: "POST", body: JSON.stringify({ character_id: characterId, guidance }) });
      navigate(backTo);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "创建失败");
    } finally {
      setBusy(false);
    }
  };

  if (broken || !scenario) {
    return (
      <section className="scenario-composer panel">
        <div className="empty empty--scroll composer-empty">          <EmptyScroll size={150} />
          <h3>这一卷不在架上</h3>
          <p>它可能尚未发布、已被撤下，或链接有误。异闻必须依附于一卷小天下集，请先挑一卷。</p>
          {error && <p className="err" role="alert">{error}</p>}
          <Link className="btn btn-primary" to="/scenarios">浏览小天下集</Link>
        </div>
      </section>
    );
  }

  return (
    <PageShell title="立异闻" subtitle={`卷：${scenario.name}`} back={{ to: backTo, label: "返回卷" }}>
      <section className="scenario-composer panel">
        <section className="scenario-console">
          <div className="scenario-picker">
            <div className="scenario-picker__head">
              <span className="eyebrow">守方奇人</span>
              <span className="scenario-picker__hint">
                {characters === null ? "载入中" : `共 ${characters.length} 位`}
                {characters !== null && characters.length > 4 && <span className="scenario-picker__more"> · 可滚</span>}
              </span>
            </div>
            <div className="scenario-picker__list" role="radiogroup" aria-label="守方奇人">
              {characters === null
                ? [0, 1, 2].map((row) => <span className="scenario-picker__ghost" key={row} />)
                : characters.map((character) => (
                    <label className="scenario-picker__row" key={character.id}>
                      <input
                        type="radio"
                        name="composer-character"
                        value={character.id}
                        checked={characterId === character.id}
                        onChange={() => setCharacterId(character.id)}
                        disabled={busy}
                      />
                      <span className="scenario-picker__mark" aria-hidden="true" />
                      <span className="scenario-picker__body">
                        <b>{character.name}</b>
                        <small>{character.bio || "未留行状"}</small>
                      </span>
                      <span className="scenario-picker__arts">{artsOf(character)}</span>
                    </label>
                  ))}
            </div>
            {characters !== null && !characters.length ? (
              <p className="scenario-picker__empty">
                尚无可用奇人，先去<Link to="/yiwenlu">异闻录</Link>收录一位。
              </p>
            ) : (
              <p className="scenario-picker__foot">选定后仍可改，公开那一刻才算数。</p>
            )}
          </div>

          <div className="scenario-sheet">
            <div className="scenario-sheet__head">
              <span className="eyebrow">指导策略</span>
              <span className="scenario-sheet__count">{guidance.length} / 1000</span>
            </div>
            <textarea
              maxLength={1000}
              rows={8}
              value={guidance}
              onChange={(event) => setGuidance(event.target.value)}
              placeholder="挑战者会读到这段提示，它决定推演时守方的应对方向；留空则不设指导。"
            />
            <div className="scenario-sheet__foot">
              <p className="muted">立异闻即公开此卷：挑战者可随时向这位奇人发起推演。</p>
              <button className="btn btn-primary" disabled={busy || !characterId} onClick={() => void create()}>
                {busy ? "正在立卷…" : "立异闻并公开"}
              </button>
            </div>
            {error && <p className="err" role="alert">{error}</p>}
          </div>
        </section>
      </section>
    </PageShell>
  );
}
