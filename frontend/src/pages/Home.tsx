import { Link } from "react-router-dom";
import { useAuth } from "../auth";
import { BookIcon, ScrollIcon } from "../components/icons";
import { SealStamp } from "../components/Ornaments";

/** 首页只保留两个入口，内容收在上半屏，山水与孤舟留给下半屏。 */
export default function Home() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <section className="home-gate">
      <header className="home-gate__greeting">
        <SealStamp char="异" size={34} />
        <h1>欢迎回来，{user.username}</h1>
      </header>
      <div className="home-gate__actions">
        <Link className="home-gate__choice home-gate__choice--world" to="/scenarios">
          <ScrollIcon size={24} />
          <strong>小天下集</strong>
          <span>展卷过招，循迹看破</span>
        </Link>
        <Link className="home-gate__choice home-gate__choice--codex" to="/yiwenlu">
          <BookIcon size={24} />
          <strong>异闻录</strong>
          <span>奇人奇术，化为己用</span>
        </Link>
      </div>
    </section>
  );
}
