// 异闻榜：名望降序排名（附见闻列），自己一行高亮；榜外也显示我的名次。
import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { TrophyIcon } from "../components/icons";

interface Entry {
  rank: number;
  username: string;
  rank_points: number;
  exp: number;
}
interface Lb {
  entries: Entry[];
  me: Entry | null;
}

const MEDALS = ["壹", "贰", "叁"];

export default function Leaderboard() {
  const { user } = useAuth();
  const [data, setData] = useState<Lb | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api<Lb>("/leaderboard").then(setData).catch((e: any) => setErr(e.message));
  }, []);

  return (
    <>
      <div className="section-head">
        <h1 className="section-title">
          <TrophyIcon size={22} /> 异闻榜
        </h1>
        <p className="muted">名望为引，见闻为注——江湖排位，尽在此榜。</p>
      </div>
      {err && <p className="err">{err}</p>}
      {!data ? (
        <div className="skeleton" style={{ height: 300 }} />
      ) : (
        <>
          <div className="leaderboard">
            {data.entries.map((e) => {
              const mine = user?.username === e.username;
              const medal = e.rank <= 3;
              return (
                <div className={`lb-row${mine ? " is-me" : ""}`} key={e.username}>
                  <span className={`lb-rank${medal ? " is-medal" : ""}`}>
                    {medal ? MEDALS[e.rank - 1] : e.rank}
                  </span>
                  <span className="lb-name">
                    {e.username}
                    {mine && <span className="lb-me-tag">我</span>}
                  </span>
                  <span className="lb-rp">{e.rank_points}</span>
                  <span className="lb-exp muted">{e.exp} 见闻</span>
                </div>
              );
            })}
          </div>
          {data.me && data.me.rank > data.entries.length && (
            <p className="muted" style={{ marginTop: 14 }}>
              我的名次：第 <b>{data.me.rank}</b> 名（{data.me.rank_points} 名望）
            </p>
          )}
        </>
      )}
    </>
  );
}
