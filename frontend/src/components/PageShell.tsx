import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ChevronLeftIcon } from "./icons";
import { CloudDivider } from "./Ornaments";

/**
 * 导航只有两条边，各自只有一种写法。这里是唯一出处，
 * DESIGN.md「导航与跳转」写下的是同一份契约。
 *
 * 向上边 → BackButton   退回上一层。全站唯一形态：34px 圆钮，骑在版心左缘外，
 *                       落在标题上方的留白带里，不参与任何内容的排版。
 * 向下边 → 由内容自身的卡片 / 行承载，不在此处封装。
 *
 * 平级跳转（去往另一个主分支）不设专门控件，由内容区的入口承担。
 */

export type BackButtonProps = { label?: string } & (
  /** 链接形态：给出目标即可 */
  | { to: string; onClick?: never }
  /** 按钮形态：需要自己接 onClick（例如返回前要拦一道「有未保存改动」） */
  | { to?: never; onClick: () => void }
);

/**
 * 页面级返回。图标钮没有可见文字，去向由 aria-label 与 title 交代；
 * 语义上它只表示「退到上一层」，不需要在按钮上写出上一层叫什么。
 */
export function BackButton(props: BackButtonProps) {
  const { label = "返回上一层" } = props;
  const icon = <ChevronLeftIcon size={16} />;
  if (props.to) {
    return (
      <Link className="nav-back" to={props.to} aria-label={label} title={label}>
        {icon}
      </Link>
    );
  }
  return (
    <button type="button" className="nav-back" onClick={props.onClick} aria-label={label} title={label}>
      {icon}
    </button>
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
  /** 返回位。false 表示这一层没有上一层（如首页） */
  back?: BackButtonProps | false;
  /** 主操作位，靠标题行右端 */
  actions?: ReactNode;
  children: ReactNode;
};

/**
 * 文档型页面的统一骨架：返回钮 ─ 标题位 ─ 主操作位，下接一行云纹分隔。
 * 沉浸式页面（ScenarioBattle / ScenarioRecords）不套用——它们的屏幕本身就是标题，
 * 但那两页里的返回钮是同一个 BackButton，只是改由 .scenario-challenge 定位。
 */
export default function PageShell({ title, subtitle, eyebrow, icon, width = "page", back, actions, children }: PageShellProps) {
  const widthClass = width === "page" ? "" : ` page-shell--${width}`;
  return (
    <div className={"page-shell" + widthClass}>
      <header className="page-shell__head">
        <div className="page-shell__title-row">
          <div className="page-shell__lead">
            {eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}
            <h1 className="section-title">
              {/* 返回钮挂在标题行内、绝对定位到标题左侧的留白里：因此纵向永远与标题同高，
                  横向不吃版心宽度。标题一个字都不用挪（见 .page-shell .nav-back） */}
              {back ? <BackButton {...back} /> : null}
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
