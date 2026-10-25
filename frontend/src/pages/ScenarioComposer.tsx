import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import PageShell from "../components/PageShell";
import { EmptyScroll } from "../components/Ornaments";

type Scenario = { id: string; slug: string; name: string };
type Character = { id: string; name: string };

/**
 * 立异闻：依托某一卷小天下集，选一位自家奇人入场并写下策略。
 * 卷的 slug 由路径参数给出，所以不存在「无卷可依」这一屏——读取失败按错误处理。
 */
export default function ScenarioComposer() {
  const navigate = useNavigate();
  const { slug = "" } = useParams();
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [characterId, setCharacterId] = useState("");
  const [guidance, setGuidance] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [broken, setBroken] = useState(false);

  const backTo = `/scenarios/${encodeURIComponent(slug)}`;

  useEffect(() => {
    let alive = true;
    setBroken(false);
    Promise.all([api<Scenario>(`/scenarios/${encodeURIComponent(slug)}`), api<Character[]>("/creator/characters")])
      .then(([item, rows]) => {
        if (!alive) return;
        setScenario(item);
        setCharacters(rows);
        setError("");
      })
      .catch((cause: Error) => {
        if (!alive) return;
        setBroken(true);
        setError(cause.message);
      });
    return () => { alive = false; };
  }, [slug]);

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
    <PageShell width="read" title="立异闻" subtitle={`卷：${scenario.name}`} back={{ to: backTo, label: "返回卷" }}>
      <section className="scenario-composer panel">
        <div className="creator-form">
        <label className="field">
          <span>选择奇人<small>{characters.length} 位可选</small></span>
          <select className="input" value={characterId} onChange={(event) => setCharacterId(event.target.value)}>
            <option value="">请选择奇人</option>
            {characters.map((character) => <option key={character.id} value={character.id}>{character.name}</option>)}
          </select>
        </label>
        {characters.length === 0 && <p className="muted">尚无可用奇人，先<Link to="/yiwenlu">去异闻录收录一位</Link>。</p>}
        <label className="field">
          <span>指导策略<small>{guidance.length}/1000</small></span>
          <textarea className="textarea" rows={8} maxLength={1000} value={guidance} onChange={(event) => setGuidance(event.target.value)} placeholder="给挑战者的策略提示" />
          <span className="hint">挑战者会读到这段提示，它决定推演时守方的应对方向。</span>
        </label>
      </div>
      {error && <p className="err" role="alert">{error}</p>}
        <div className="creator-canvas__actions">
          <button className="btn btn-primary" disabled={busy} onClick={() => void create()}>立异闻并公开</button>
        </div>
      </section>
    </PageShell>
  );
}
