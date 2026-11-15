import { useEffect, useRef, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import UserMenu from "./UserMenu";
import InkLandscape from "./InkLandscape";
import RosterGuessLayer from "./RosterGuessLayer";

export default function AppFrame({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const main = useRef<HTMLElement>(null);
  const previous = useRef(pathname);
  useEffect(() => {
    if (previous.current === pathname) return;
    previous.current = pathname;
    window.scrollTo({ top: 0 });
    main.current?.focus({ preventScroll: true });
  }, [pathname]);
  return <div className="app app-redesign">
    <InkLandscape />
    <a className="skip-link" href="#main-content">跳到主要内容</a>
    <UserMenu />
    <div className="eaves" aria-hidden="true" />
    <main className="container" id="main-content" tabIndex={-1} ref={main}>{children}</main>
    <RosterGuessLayer />
  </div>;
}
