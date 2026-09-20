import { Link } from "react-router-dom";
import { useAuth } from "../auth";
import { BookIcon, ScrollIcon } from "../components/icons";
import { SealStamp } from "../components/Ornaments";

/** 登录后首页：占位枢纽 —— 居中问候，两按钮分流小天下集与异闻录。 */
export default function Home() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <section className="home-gate">
      <span className="home-gate__seal" aria-hidden="true">
        <SealStamp char="异" size={44} />
      </span>
      <h1 className="section-title">{user.username}，落座</h1>
      <p className="muted">要去哪处书场？</p>
      <div className="home-gate__actions">
        <Link className="home-gate__choice" to="/scenarios">
          <ScrollIcon size={20} />
          <strong>小天下集</strong>
          <span>择一卷册，挑战各路奇人</span>
        </Link>
        <Link className="home-gate__choice" to="/abilities">
          <BookIcon size={20} />
          <strong>异闻录</strong>
          <span>收录自己的奇人与奇术</span>
        </Link>
      </div>
    </section>
  );
}
