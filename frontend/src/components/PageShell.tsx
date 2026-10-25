import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ChevronLeftIcon, ChevronRightIcon } from "./icons";
import { CloudDivider } from "./Ornaments";

/**
 * 跳转的三类边，各自只有一种写法。这里是那三种写法的唯一出处，
 * DESIGN.md 的「导航与跳转」章节写下的是同一份契约。
 *
 * 向上边 → BackLink     退回上一层（左向箭头 + 文字）
 * 平级边 → EntryLink    横向进入另一个分支（文字 + 右向箭头）
 * 向下边 → 由内容自身的卡片 / 行承载，不在此处
 */

export type BackLinkProps = { label?: string } & (
  /** 链接形态：给出目标即可 */
  | { to: string; as?: "link" }
  /** 按钮形态：需要自己接 onClick（例如返回前要拦一道「有未保存改动」） */
  | { as: "button"; onClick: () => void }
);

export function BackLink(props: BackLinkProps) {
  const { label = "返回" } = props;
  const body = (
    <>
      <ChevronLeftIcon size={14} />
      <span>{label}</span>
    </>
  );
  if (props.as === "button") {
    return (
      <button type="button" className="nav-back" onClick={props.onClick}>
        {body}
      </button>
    );
  }
  return (
    <Link className="nav-back" to={props.to}>
      {body}
    </Link>
  );
}

export type EntryLinkProps = {
  /** 平级边的目标 */
  to: string;
  children: ReactNode;
  title?: string;
};

/** 平级边：横向去往另一个主分支。箭头在右侧，与向上边的左向箭头方向相反。 */
export function EntryLink({ to, children, title }: EntryLinkProps) {
  return (
    <Link className="nav-entry" to={to} title={title}>
      <span>{children}</span>
      <ChevronRightIcon size={14} />
    </Link>
  );
}

export type PageShellProps = {
  title: ReactNode;
  subtitle?: ReactNode;
  eyebrow?: ReactNode;
  icon?: ReactNode;
  /**
   * 版心宽度。全站只有三档，按内容形态选，不按页面喜好选：
   *   page（默认 1080）— 常规文档页
   *   wide（1180）      — 双栏工作台、后台表格这类信息密度高的页面
   *   read（760）       — 表单与长文，保证输入行长舒适
   */
  width?: "page" | "wide" | "read";
  /** ① 返回位。false 表示这一层没有上一层（如首页） */
  back?: BackLinkProps | false;
  /** ③ 主操作位 */
  actions?: ReactNode;
  children: ReactNode;
};

/**
 * 文档型页面的统一骨架：返回位 ─ 标题位 ─ 主操作位，下接一行云纹分隔。
 * 沉浸式页面（ScenarioBattle / ScenarioRecords）不套用——它们的屏幕本身就是标题。
 */
export default function PageShell({ title, subtitle, eyebrow, icon, width = "page", back, actions, children }: PageShellProps) {
  const widthClass = width === "page" ? "" : ` page-shell--${width}`;
  return (
    <div className={"page-shell" + widthClass}>
      <header className="page-shell__head">
        {/* 返回独占标题上方一行：位置不受主操作数量影响，全站恒定 */}
        <div className="page-shell__back-row">{back ? <BackLink {...back} /> : null}</div>
        <div className="page-shell__title-row">
          <div className="page-shell__lead">
            {eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}
            <h1 className="section-title">
              {icon}
              {title}
            </h1>
            {subtitle ? <p className="muted">{subtitle}</p> : null}
          </div>
          {actions ? <div className="page-shell__side">{actions}</div> : null}
        </div>
      </header>
      <CloudDivider />
      {children}
    </div>
  );
}
