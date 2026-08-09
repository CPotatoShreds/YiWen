// 装饰性水墨元素：灯笼 / 幡旗 / 远山 / 侠客剪影。
// 纯内联 SVG，零依赖，贴合古镇纸墨主题。填色用 CSS 变量（--accent / --ink…），随主题联动。
import type { SVGProps } from "react";

export interface OrnamentProps extends SVGProps<SVGSVGElement> {
  size?: number;
}

/** 朱砂纸灯笼：提绳 + 竹骨 + 灯身 + 穗。竖长形，高约为宽的 56/36。 */
export function Lantern({ size = 30, ...rest }: OrnamentProps) {
  return (
    <svg width={size} height={size * (56 / 36)} viewBox="0 0 36 56" aria-hidden="true" {...rest}>
      {/* 提绳 */}
      <line x1="18" y1="0" x2="18" y2="5.5" stroke="var(--ink)" strokeWidth="1.2" />
      {/* 上盖 */}
      <path d="M12.5 6.5 h11 l1.5 -2.5 h-14 z" fill="var(--accent-strong)" />
      {/* 灯身（圆角竖体） */}
      <rect x="9.5" y="8.5" width="17" height="25" rx="7" fill="var(--accent)" />
      <path d="M10.5 20 q -0.4 4 0 8" stroke="var(--accent-strong)" strokeWidth="0.7" fill="none" />
      {/* 竹骨 */}
      <path d="M15 10 q 1.6 11 0 22" stroke="var(--accent-strong)" strokeWidth="0.9" fill="none" opacity="0.8" />
      <path d="M18 9.5 v23" stroke="var(--accent-strong)" strokeWidth="0.9" fill="none" opacity="0.7" />
      <path d="M21 10 q -1.6 11 0 22" stroke="var(--accent-strong)" strokeWidth="0.9" fill="none" opacity="0.8" />
      {/* 高光 */}
      <path d="M12.5 14 q -0.4 9 0 17" stroke="var(--surface)" strokeWidth="0.7" fill="none" opacity="0.35" />
      {/* 下盖 */}
      <path d="M12.5 36.5 h11 l-1.5 2.5 h-8 z" fill="var(--accent-strong)" />
      {/* 穗 */}
      <path d="M16 40 h4 v5 q -2 2.4 -4 2.4 q -2 0 -4 -2.4 v-5 h4 z" fill="var(--accent)" />
      <line x1="18" y1="47.4" x2="18" y2="54" stroke="var(--accent-strong)" strokeWidth="1" />
    </svg>
  );
}

/** 毛笔：笔杆 + 笔斗 + 收尖笔毫。白色（--surface），用于朱砂底上的「对决中」指示。 */
export function Brush({ size = 26, ...rest }: OrnamentProps) {
  return (
    <svg width={size} height={size * (58 / 40)} viewBox="0 0 40 58" aria-hidden="true" {...rest}>
      {/* 笔杆 */}
      <rect x="16" y="3" width="8" height="30" rx="4" fill="var(--surface)" />
      {/* 笔杆顶帽 */}
      <rect x="15.6" y="2.2" width="8.8" height="5" rx="2.5" fill="var(--surface)" opacity="0.85" />
      {/* 笔斗（箍） */}
      <path d="M15.6 33 h8.8 l-1.4 4.6 h-6 z" fill="var(--surface)" opacity="0.85" />
      {/* 笔毫（收尖） */}
      <path d="M15.8 37.6 h8.4 l-2.2 15.5 Q 20 57.5 19.6 55 Z" fill="var(--surface)" />
    </svg>
  );
}

/** 挂幡：旗杆 + 开衩幡旗，旗面题「幡」字。高约为宽的 84/56。 */
export function BattleBanner({ size = 44, ...rest }: OrnamentProps) {
  return (
    <svg width={size} height={size * (84 / 56)} viewBox="0 0 56 84" aria-hidden="true" {...rest}>
      {/* 旗杆 */}
      <rect x="12" y="2" width="2.6" height="80" rx="1.3" fill="var(--ink)" />
      {/* 顶球 */}
      <circle cx="13.3" cy="4.5" r="3" fill="var(--accent)" />
      {/* 幡旗（下摆开衩，随风飘） */}
      <path
        d="M14.6 8 H 40 Q 45 13 45 21 Q 45 27 41 29 L 28 26.5 L 32 35.5 L 14.6 38 Z"
        fill="var(--accent)"
      />
      <path d="M14.6 8 Q 30 9 40 16" fill="none" stroke="var(--accent-strong)" strokeWidth="1" opacity="0.7" />
      <path d="M28 26.5 L 32 35.5 L 14.6 38" fill="none" stroke="var(--accent-strong)" strokeWidth="0.8" opacity="0.6" />
      {/* 旗面题字 */}
      <text
        x="29.5"
        y="25"
        textAnchor="middle"
        fontFamily="'Kaiti SC','STKaiti','PingFang SC',serif"
        fontSize="11"
        fontWeight="700"
        fill="var(--surface)"
      >
        幡
      </text>
    </svg>
  );
}

/** 远山剪影：三层深浅墨色山脊。默认等比铺满容器宽。 */
export function InkMountains({ size, ...rest }: OrnamentProps) {
  return (
    <svg
      viewBox="0 0 1200 200"
      width={size}
      height={size ? undefined : "auto"}
      preserveAspectRatio="xMidYMax meet"
      aria-hidden="true"
      {...rest}
    >
      <g fill="var(--ink)">
        {/* 远层 */}
        <path
          d="M0 200 L0 168 L96 96 L152 150 L244 64 L330 158 L428 108 L516 178 L596 120 L706 58 L792 156 L884 96 L982 188 L1082 128 L1200 186 L1200 200 Z"
          opacity="0.06"
        />
        {/* 中层 */}
        <path
          d="M0 200 L0 186 L140 132 L262 204 L382 152 L524 208 L646 158 L782 202 L902 148 L1042 206 L1200 172 L1200 200 Z"
          opacity="0.11"
        />
        {/* 近层 */}
        <path
          d="M0 200 L0 196 L190 168 L310 202 L462 176 L600 200 L762 172 L920 200 L1080 180 L1200 198 L1200 200 Z"
          opacity="0.16"
        />
      </g>
    </svg>
  );
}

/** 侠客剪影：月牙 + 断崖 + 斗笠剑客 + 远山。用于认证页「书坊正门」的背景。 */
export function SwordsmanScene({ size = 210, ...rest }: OrnamentProps) {
  return (
    <svg
      width={size}
      height={size * (220 / 200)}
      viewBox="0 0 200 220"
      preserveAspectRatio="xMidYMax meet"
      aria-hidden="true"
      {...rest}
    >
      {/* 月牙（双圆 evenodd 镂空，开口朝左上） */}
      <path
        fillRule="evenodd"
        d="M150 36 m -24 0 a 24 24 0 1 0 48 0 a 24 24 0 1 0 -48 0
           M156 44 m -17 0 a 17 17 0 1 0 34 0 a 17 17 0 1 0 -34 0"
        fill="var(--ink)"
        opacity="0.55"
      />
      {/* 远山 */}
      <path d="M-10 176 Q 30 128 72 178 Q 96 158 128 180" fill="none" stroke="var(--ink)" strokeWidth="2.5" opacity="0.18" />
      <path d="M56 200 Q 112 148 168 200" fill="none" stroke="var(--ink)" strokeWidth="3" opacity="0.14" />
      {/* 断崖 */}
      <path d="M6 200 L 56 200 L 50 128 L 14 128 Z" fill="var(--ink)" opacity="0.10" />
      {/* 侠客：斗笠 + 袍 + 执剑 */}
      <g fill="var(--ink)">
        {/* 斗笠 */}
        <path d="M29 60 Q 45 44 61 60 Q 54 64 45 64 Q 36 64 29 60 Z" />
        <path d="M37 58 Q 45 47 53 58 Q 45 61 37 58 Z" />
        {/* 头 */}
        <path d="M41 62 h6 v6 q -3 2 -6 2 q -3 0 -6 -2 Z" />
        {/* 袍 */}
        <path d="M38 70 l -3 40 q 9 6 18 0 l -3 -40 q -6 4 -12 0 Z" />
        <path d="M35 108 q -6 3 -10 1 l 4 -5 q 4 2 6 2 Z" />
        {/* 执剑右臂 */}
        <path d="M51 72 l 8 -8 q 3 -1 4 2 l -9 8 Z" />
        {/* 剑 + 护手 */}
        <path d="M57 62 L 84 38 l 3 4 l -28 24 Z" />
        <path d="M57 64 l 6 -3" stroke="var(--ink)" strokeWidth="2.5" strokeLinecap="round" fill="none" />
      </g>
    </svg>
  );
}
