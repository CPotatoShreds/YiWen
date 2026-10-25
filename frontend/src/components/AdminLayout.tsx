import { NavLink, Outlet } from "react-router-dom";
import PageShell from "./PageShell";
import { BarChart3Icon, BookIcon, ScrollIcon, TargetIcon, UsersIcon } from "./icons";

const links = [
  { to: "/admin", label: "仪表盘", icon: TargetIcon, end: true },
  { to: "/admin/users", label: "异闻师", icon: UsersIcon },
  { to: "/admin/scenarios", label: "小天下集审核", icon: ScrollIcon },
  { to: "/admin/abilities", label: "奇术", icon: BookIcon },
  { to: "/admin/traffic", label: "流量", icon: BarChart3Icon },
];

export default function AdminLayout() {
  return (
    <PageShell
      width="wide"
      eyebrow="异闻司"
      title="后台案牍"
      subtitle="只为管理员开放的异闻录内务"
      back={{ to: "/home", label: "返回首页" }}
    >
      <nav className="admin-subnav" aria-label="后台导航">
        {links.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className={({ isActive }) => isActive ? "is-active" : ""}>
            <Icon size={15} /> {label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </PageShell>
  );
}
