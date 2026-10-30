import { Link } from "react-router-dom";
import { useAuth } from "../auth";
import PageShell from "../components/PageShell";
import { GearIcon } from "../components/icons";

/** 用户信息页：只读占位 —— 展示当前账号基础信息，后续再迭代。 */
export default function Me() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <PageShell title="我的账号" subtitle="你在这个异闻师身份下的凭据" back={{ to: "/home", label: "返回首页" }}>
      <section className="me-page">
        <div className="me-card">
          <span className="me-card__avatar" aria-hidden="true">
            {user.username.slice(0, 1)}
          </span>
          <h2 className="me-card__name">{user.username}</h2>
          {user.is_admin && <span className="me-card__badge">管理员</span>}
          <dl className="me-card__fields">
            <div>
              <dt>用户名</dt>
              <dd>{user.username}</dd>
            </div>
            <div>
              <dt>邮箱</dt>
              <dd>{user.email || "未绑定"}</dd>
            </div>
          </dl>
          <div className="me-card__actions">
            <Link className="btn btn-primary" to="/settings">
              <GearIcon size={15} /> 前往设置
            </Link>
          </div>
        </div>
      </section>
    </PageShell>
  );
}
