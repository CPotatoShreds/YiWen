import { Link, NavLink, Outlet } from "react-router-dom";
import { BarChart3Icon, BookIcon, ScrollIcon, TargetIcon, UsersIcon } from "./icons";
import { CloudDivider } from "./Ornaments";

const links = [
  { to: "/admin", label: "仪表盘", icon: TargetIcon, end: true },
  { to: "/admin/users", label: "异闻师", icon: UsersIcon },
  { to: "/admin/scenarios", label: "小天下集审核", icon: ScrollIcon },
  { to: "/admin/abilities", label: "奇术", icon: BookIcon },
  { to: "/admin/traffic", label: "流量", icon: BarChart3Icon },
];

export default function AdminLayout() {
  return (
    <div className="admin-shell">
      <div className="section-head admin-heading">
        <div>
          <span className="eyebrow">异闻司</span>
          <h1 className="section-title">后台案牍</h1>
        </div>
        <p className="muted">只为管理员开放的异闻录内务</p>
        <div className="section-head__exit">
          <Link className="muted" to="/home">返回首页</Link>
        </div>
      </div>
      <CloudDivider />
      <nav className="admin-subnav" aria-label="后台导航">
        {links.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className={({ isActive }) => isActive ? "is-active" : ""}>
            <Icon size={15} /> {label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  );
}
