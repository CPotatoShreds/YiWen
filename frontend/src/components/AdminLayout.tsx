import { NavLink, Outlet } from "react-router-dom";
import { BarChart3Icon, BookIcon, GearIcon, SwordIcon, TargetIcon, TestTubeIcon, UsersIcon } from "./icons";

const links = [
  { to: "/admin", label: "仪表盘", icon: TargetIcon, end: true },
  { to: "/admin/users", label: "异闻师", icon: UsersIcon },
  { to: "/admin/abilities", label: "奇术", icon: BookIcon },
  { to: "/admin/battles", label: "行迹", icon: GearIcon },
  { to: "/admin/relations", label: "关系", icon: UsersIcon },
  { to: "/admin/traffic", label: "流量", icon: BarChart3Icon },
  { to: "/admin/test", label: "试验场", icon: TestTubeIcon },
  { to: "/admin/test/core-guess", label: "核心一句话", icon: SwordIcon }, // 临时试验：删除时连同页面一并移除
];

export default function AdminLayout() {
  return (
    <div className="admin-shell">
      <div className="section-head admin-heading">
        <div>
          <span className="eyebrow">CONTROL ROOM</span>
          <h1 className="section-title">后台案牍</h1>
        </div>
        <p className="muted">只为管理员开放的异闻录内务</p>
      </div>
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
