import { useEffect, useRef, type ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import * as Dialog from "@radix-ui/react-dialog";
import { useAuth } from "../auth";
import UserMenu from "./UserMenu";
import InkLandscape from "./InkLandscape";
import { SealStamp } from "./Ornaments";

const destinations = [
  { to: "/home", label: "书院" },
  { to: "/scenarios", label: "小天下集" },
  { to: "/yiwenlu", label: "我的异闻录" },
  { to: "/settings", label: "设置" },
];

export default function AppFrame({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const main = useRef<HTMLElement>(null);
  const previous = useRef(pathname);
  useEffect(() => {
    if (previous.current === pathname) return;
    previous.current = pathname;
    window.scrollTo({ top: 0 });
    main.current?.focus({ preventScroll: true });
    if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      main.current?.animate([{ opacity: 0, transform: "translateY(6px)" }, { opacity: 1, transform: "translateY(0)" }], { duration: 180, easing: "ease-out" });
    }
  }, [pathname]);
  return <div className="app app-redesign">
    <InkLandscape />
    <a className="skip-link" href="#main-content">跳到主要内容</a>
    <header className="site-header">
      <Link className="site-brand" to="/home"><SealStamp char="异" size={34} /><strong>异闻录</strong><span className="site-brand-note">以奇术，见天地</span></Link>
      {user && <nav className="site-nav" aria-label="主导航">{destinations.map(item => <NavLink key={item.to} to={item.to}>{item.label}</NavLink>)}</nav>}
      <div className="site-header-actions"><UserMenu />
        {user && <Dialog.Root key={pathname}><Dialog.Trigger className="mobile-menu-button" aria-label="打开导航">目录</Dialog.Trigger><Dialog.Portal>
          <Dialog.Overlay className="ds-overlay" />
          <Dialog.Content className="mobile-menu"><Dialog.Title>异闻录 · 目录</Dialog.Title><Dialog.Description>前往书院、浏览卷或管理自己的奇人奇术。</Dialog.Description>
            <nav aria-label="移动端导航">{destinations.map(item => <Dialog.Close key={item.to} asChild><NavLink to={item.to}>{item.label}</NavLink></Dialog.Close>)}</nav>
            <Dialog.Close className="btn">关闭目录</Dialog.Close>
          </Dialog.Content></Dialog.Portal></Dialog.Root>}
      </div>
    </header>
    <main className="container" id="main-content" tabIndex={-1} ref={main}>{children}</main>
    <footer className="site-footer"><span>异闻录 · 每一种奇思，都有回响</span><div><Link to="/terms">用户协议</Link><Link to="/privacy">隐私政策</Link></div></footer>
  </div>;
}
