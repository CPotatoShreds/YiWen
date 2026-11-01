import { Link } from "react-router-dom";
import { useAuth } from "../auth";
import { BookIcon, ScrollIcon } from "../components/icons";
import { SealStamp } from "../components/Ornaments";
import InkFish from "../components/InkFish";

/** 登录后首页：居中问候，两按钮分流小天下集与异闻录；右下角一池墨鱼。 */
export default function Home() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <section className="home-gate">
      <InkFish />
      <span className="home-gate__seal" aria-hidden="true">
        <SealStamp char="异" size={44} />
      </span>
      <h1 className="section-title">欢迎回来，{user.username}</h1>
      <div className="home-gate__actions">
        <Link className="home-gate__choice" to="/scenarios">
          <ScrollIcon size={20} />
          <strong>小天下集</strong>
          <span>天下异闻，尽汇于此</span>
        </Link>
        <Link className="home-gate__choice" to="/yiwenlu">
          <BookIcon size={20} />
          <strong>异闻录</strong>
          <span>奇人奇术，化为己用</span>
        </Link>
      </div>
    </section>
  );
}
