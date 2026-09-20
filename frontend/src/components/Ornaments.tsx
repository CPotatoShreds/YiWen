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

/** 白文印章：朱砂印面 + 留白印文（阴刻）。印面略有刀痕，印泥有未匀处。 */
export function SealStamp({
  char = "异",
  size = 34,
  ...rest
}: OrnamentProps & { char?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true" {...rest}>
      {/* 印面：四边微有起伏，模拟刀刻 */}
      <path
        d="M4.6 3.4 Q 20 2.2 35.4 3.5 Q 37.6 20 35.3 36.6 Q 20 37.8 4.7 36.4 Q 2.3 20 4.6 3.4 Z"
        fill="var(--accent)"
      />
      {/* 内栏：一道深朱砂细线，做出印面厚度（不是白框） */}
      <path
        d="M8.2 6.8 Q 20 6 31.8 6.9 Q 33.2 20 31.7 33.1 Q 20 33.9 8.3 33 Q 6.8 20 8.2 6.8 Z"
        fill="none"
        stroke="var(--accent-strong)"
        strokeWidth="0.9"
        opacity="0.5"
      />
      {/* 印泥未匀处 */}
      <g fill="var(--surface)" opacity="0.12">
        <circle cx="12.5" cy="12.6" r="1.4" />
        <circle cx="28.6" cy="27.4" r="1.7" />
      </g>
      <text
        x="20"
        y="29.6"
        textAnchor="middle"
        fontFamily="'Kaiti SC','STKaiti','KaiTi','楷体','PingFang SC',serif"
        fontSize="25"
        fontWeight="500"
        fill="var(--surface)"
      >
        {char}
      </text>
    </svg>
  );
}

/** 云纹分隔：两侧细横线 + 朱砂如意珠。用于区块抬头之间的收束。 */
export function CloudDivider({ className }: { className?: string }) {
  return (
    <svg
      className={className ? `cloud-divider ${className}` : "cloud-divider"}
      viewBox="0 0 240 16"
      height="16"
      aria-hidden="true"
    >
      <g stroke="var(--line-strong)" strokeWidth="1" strokeLinecap="round">
        <path d="M4 8 H104" opacity="0.7" />
        <path d="M136 8 H236" opacity="0.7" />
      </g>
      <g fill="var(--line-strong)" opacity="0.55">
        <circle cx="110.5" cy="8" r="1.5" />
        <circle cx="129.5" cy="8" r="1.5" />
      </g>
      <path d="M120 2.4 L125.6 8 L120 13.6 L114.4 8 Z" fill="var(--accent)" />
    </svg>
  );
}

/** 空卷：一轴未落墨的纸笺 + 朱砂空印。用于各处空态插画。 */
export function EmptyScroll({ size = 150, className, ...rest }: OrnamentProps) {
  return (
    <svg
      className={className ? `empty-scroll ${className}` : "empty-scroll"}
      width={size}
      height={size * (108 / 160)}
      viewBox="0 0 160 108"
      preserveAspectRatio="xMidYMid meet"
      aria-hidden="true"
      {...rest}
    >
      <g fill="var(--ink)">
        {/* 左轴 */}
        <rect x="8" y="22" width="11" height="64" rx="5.5" opacity="0.16" />
        <ellipse cx="13.5" cy="22" rx="5.5" ry="2.8" opacity="0.2" />
        <ellipse cx="13.5" cy="86" rx="5.5" ry="2.8" opacity="0.2" />
        {/* 右轴（半露） */}
        <rect x="143" y="30" width="9" height="50" rx="4.5" opacity="0.13" />
        <ellipse cx="147.5" cy="30" rx="4.5" ry="2.4" opacity="0.17" />
        <ellipse cx="147.5" cy="80" rx="4.5" ry="2.4" opacity="0.17" />
      </g>
      {/* 纸面 */}
      <path
        d="M19 20 H144 V88 H19 Z"
        fill="var(--surface)"
        stroke="var(--line-strong)"
        strokeWidth="1"
      />
      {/* 朱丝栏（未写字的行） */}
      <g stroke="var(--line)" strokeWidth="1" strokeLinecap="round">
        <path d="M32 36 H130" />
        <path d="M32 49 H130" />
        <path d="M32 62 H130" />
        <path d="M32 75 H104" />
      </g>
      {/* 空印 */}
      <path
        d="M108 58 h15 v15 h-15 z"
        fill="none"
        stroke="var(--accent)"
        strokeWidth="1.4"
        strokeDasharray="3 2.6"
        opacity="0.5"
      />
    </svg>
  );
}

/** 奇术卡背：双线边栏 + 四角回纹 + 中心圆光。铺满容器，用于未看破的卡。 */
export function CardBack({ className }: { className?: string }) {
  return (
    <svg
      className={className ? `card-back ${className}` : "card-back"}
      viewBox="0 0 132 180"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <g fill="none" stroke="var(--line-strong)">
        <rect x="5.5" y="5.5" width="121" height="169" rx="5" strokeWidth="1.1" opacity="0.8" />
        <rect x="10.5" y="10.5" width="111" height="159" rx="3" strokeWidth="1" opacity="0.5" />
      </g>
      {/* 四角回纹 */}
      <g fill="none" stroke="var(--line-strong)" strokeWidth="1" opacity="0.7">
        <path d="M14 24 V18 H20" />
        <path d="M118 24 V18 H112" />
        <path d="M14 156 V162 H20" />
        <path d="M118 156 V162 H112" />
      </g>
      {/* 中心圆光 */}
      <g fill="none" stroke="var(--line-strong)">
        <circle cx="66" cy="90" r="34" strokeWidth="1" opacity="0.45" />
        <circle cx="66" cy="90" r="27" strokeWidth="1" opacity="0.3" strokeDasharray="4 3.5" />
      </g>
      <g fill="var(--accent)" opacity="0.22">
        <path d="M66 74 L70 90 L66 106 L62 90 Z" />
        <path d="M50 90 L66 86 L82 90 L66 94 Z" />
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
