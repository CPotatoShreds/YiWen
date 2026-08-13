import { Link, NavLink } from "react-router-dom";
import { useAuth } from "../auth";
import StatNumber from "./StatNumber";
import { BookIcon, GearIcon, LogoutIcon, ScrollIcon, TrophyIcon } from "./icons";

export default function Navbar() {
  const { user, logout } = useAuth();
  return (
    <nav className="nav">
      <Link to="/" className="brand">
        <span className="brand__mark">
          <BookIcon size={17} />
        </span>
        异闻录
      </Link>
      {user && (
        <>
          <NavLink
            to="/"
            className={({ isActive }) => "nav__link" + (isActive ? " is-active" : "")}
            end
          >
            驿路
          </NavLink>
          <NavLink
            to="/abilities"
            className={({ isActive }) => "nav__link" + (isActive ? " is-active" : "")}
          >
            异闻录
          </NavLink>
          <NavLink
            to="/books"
            className={({ isActive }) => "nav__link" + (isActive ? " is-active" : "")}
          >
            行迹
          </NavLink>
          <NavLink
            to="/leaderboard"
            className={({ isActive }) => "nav__link" + (isActive ? " is-active" : "")}
          >
            <TrophyIcon size={14} />
            异闻榜
          </NavLink>
          <NavLink
            to="/board"
            className={({ isActive }) => "nav__link" + (isActive ? " is-active" : "")}
          >
            <ScrollIcon size={14} />
            奇人榜
          </NavLink>
          <NavLink
            to="/friends"
            className={({ isActive }) => "nav__link" + (isActive ? " is-active" : "")}
          >
            故人
          </NavLink>
          {user.is_admin && (
            <NavLink
              to="/admin"
              className={({ isActive }) => "nav__link" + (isActive ? " is-active" : "")}
            >
              <GearIcon size={14} />
              管理
            </NavLink>
          )}
          <NavLink
            to="/settings"
            className={({ isActive }) => "nav__link" + (isActive ? " is-active" : "")}
          >
            设置
          </NavLink>
          <span className="nav__user">
            {user.username}
            <span className="rp" title="名望"><StatNumber value={user.rank_points} /></span>
          </span>
          <button className="btn btn-ghost btn-sm btn-icon" onClick={logout} title="退出登录" aria-label="退出登录">
            <LogoutIcon size={16} />
          </button>
        </>
      )}
    </nav>
  );
}
