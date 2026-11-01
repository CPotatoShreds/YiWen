/**
 * 推演占位的墨迹生成器——移植自 ink-v4「柔锋相间」，只留算法，去掉全部调参界面。
 *
 * 坐标系是生成器自己的「单位空间」：一行高恒为 UNIT_LINE_GAP，字形、笔画、间距都按这个尺度调好。
 * 落笔时整体乘一个 k = 行高 / UNIT_LINE_GAP，于是每个行距必然等于一条书页格线，
 * 38px 与 33px 两档行高不用各写一套。行距因此不再是参数，它被格线接管。
 *
 * 字形取自两套骨架：FORMS 是圆转连笔（柔字），GLYPHS 是提按收锋（锋字），
 * 按 INK_PARAMS.sharpness 逐字混排。每笔的点都带半径，靠 segment() 画成锥形笔迹。
 */

/** 截图那一版的参数。改这里就是改风格；行距与行数不在此列（见文件头）。 */
export const INK_PARAMS = {
  spacing: 49, // 笔势间距：字与字的推进量（单位空间）
  link: 60, // 勾连程度：相邻两笔接成连笔的概率
  weight: 3.8, // 笔画粗细
  sway: 51, // 纵向起伏：整行随机上下偏移的幅度
  pressure: 78, // 提按变化
  dry: 32, // 飞白质感
  linkWidth: 32, // 牵丝粗细
  sharpness: 57, // 锋字占比
} as const;

export type InkParams = {
  -readonly [K in keyof typeof INK_PARAMS]: number;
};

/** 一行在单位空间里的高度。画布缩放 k = 行高 / UNIT_LINE_GAP。 */
export const UNIT_LINE_GAP = 68;

/** 画布底部留白（单位空间）：够到最后一行压线的笔锋，不至于被裁掉。 */
export const TAIL_UNITS = 40;

/** 行与行之间的停顿（单位空间，约等于 510ms）——原页同值。 */
const ROW_GAP = 510;

type SharpKind = "bar" | "stem" | "reach" | "sweep";

export type InkPoint = {
  x: number;
  y: number;
  /** 笔宽的一半，逐点变化形成提按。 */
  r: number;
  grain: boolean;
  fiber: number;
  /** 沿笔画的累计长度，用来按里程推进。 */
  d: number;
};

export type InkStroke = {
  pts: InkPoint[];
  line: number;
  group: number;
  start: number;
  duration: number;
  length: number;
};

/** 线性同余，种子固定即笔迹固定（原页同一套常数）。 */
class Rng {
  private state: number;

  constructor(seed: number) {
    this.state = seed >>> 0;
  }

  next(): number {
    this.state = (Math.imul(this.state, 1664525) + 1013904223) >>> 0;
    return this.state / 4294967296;
  }

  range(min: number, max: number): number {
    return min + (max - min) * this.next();
  }
}

/** 16 套柔字骨架：每条是三次贝塞尔的点列，只取笔势，不构成真正的字。 */
const FORMS: number[][][] = [
  [[9, 5, 19, 0, 32, 6, 27, 13, 24, 18, 13, 16, 6, 24], [5, 23, 15, 16, 35, 15, 31, 22, 27, 30, 10, 24, 14, 34, 18, 40, 30, 34, 39, 30], [23, 18, 21, 29, 22, 37, 17, 47]],
  [[7, 9, 13, 7, 22, 5, 31, 8], [23, 2, 24, 13, 12, 22, 7, 34], [14, 21, 24, 15, 36, 16, 31, 23, 25, 28, 17, 29, 20, 37, 24, 43, 35, 35, 39, 30]],
  [[5, 5, 15, 9, 15, 15, 9, 20], [22, 5, 17, 12, 19, 19, 29, 17, 40, 14, 35, 27, 26, 34], [18, 21, 12, 30, 16, 39, 7, 46], [25, 30, 29, 36, 35, 38, 40, 36]],
  [[9, 9, 20, 3, 35, 9, 30, 15, 26, 20, 9, 21, 8, 29], [17, 6, 15, 18, 23, 21, 18, 31, 12, 43, 28, 40, 36, 36], [30, 24, 33, 28, 36, 30, 39, 30]],
  [[8, 5, 6, 16, 2, 24, 5, 30], [18, 8, 30, 0, 39, 10, 27, 17, 17, 24, 9, 26, 12, 34], [20, 18, 27, 24, 34, 20, 30, 28, 26, 39, 14, 43, 6, 46]],
  [[11, 4, 16, 7, 18, 11, 17, 16], [5, 21, 16, 14, 30, 16, 35, 13], [26, 19, 29, 25, 9, 29, 13, 35, 17, 42, 34, 36, 37, 33], [23, 26, 22, 36, 21, 42, 15, 48]],
  [[3, 15, 9, 7, 22, 4, 27, 9, 34, 17, 14, 18, 12, 25], [13, 18, 11, 29, 16, 40, 8, 46], [22, 25, 30, 22, 38, 26, 33, 31, 29, 36, 26, 39, 34, 40]],
  [[9, 4, 18, 6, 21, 13, 13, 19], [29, 3, 23, 14, 20, 23, 16, 29], [6, 29, 14, 24, 35, 22, 36, 27, 37, 32, 28, 33, 26, 36, 23, 40, 30, 40, 39, 35]],
  [[7, 10, 16, 9, 30, 0, 34, 8, 38, 15, 22, 16, 17, 22], [22, 6, 20, 17, 11, 28, 7, 36], [19, 27, 24, 25, 32, 23, 32, 30, 30, 37, 19, 43, 11, 46]],
  [[12, 5, 7, 14, 8, 20, 15, 19], [26, 6, 34, 11, 32, 20, 23, 23, 12, 28, 5, 32, 8, 37], [18, 31, 28, 26, 34, 30, 29, 37, 23, 42, 32, 43, 39, 39]],
  [[6, 10, 13, 4, 22, 5, 23, 10], [31, 6, 25, 14, 13, 20, 9, 29], [17, 18, 25, 15, 34, 19, 30, 24, 25, 31, 17, 28, 19, 34, 21, 41, 32, 39, 40, 34]],
  [[8, 5, 17, 9, 16, 16, 10, 23], [25, 4, 33, 3, 35, 13, 27, 18], [9, 29, 17, 21, 32, 20, 31, 28, 29, 33, 19, 36, 17, 45], [29, 33, 32, 35, 36, 35, 40, 32]],
  [[5, 13, 17, 7, 31, 5, 34, 9], [18, 7, 19, 17, 5, 26, 8, 31], [28, 17, 21, 22, 18, 31, 23, 35, 29, 39, 36, 34, 39, 29], [14, 33, 10, 39, 10, 43, 5, 47]],
  [[13, 4, 19, 6, 21, 11, 17, 15], [5, 22, 17, 13, 32, 15, 33, 21, 33, 26, 18, 27, 15, 32], [25, 26, 25, 34, 13, 42, 9, 45], [22, 35, 27, 36, 36, 35, 39, 32]],
  [[4, 12, 13, 10, 19, 7, 25, 5], [13, 9, 12, 20, 5, 31, 10, 34], [24, 16, 34, 11, 38, 19, 29, 23, 17, 30, 17, 37, 24, 38, 30, 39, 35, 33, 37, 28]],
  [[9, 4, 12, 10, 12, 14, 7, 18], [23, 6, 32, 3, 37, 13, 27, 17, 18, 21, 13, 24, 11, 30], [18, 28, 23, 25, 33, 27, 29, 33, 26, 38, 22, 41, 15, 47]],
];

/** 20 套锋字骨架：横（bar）、竖（stem）、长撇捺（reach）、扫（sweep）。 */
const GLYPHS: { w: number; p: [SharpKind, number[]][] }[] = [
  { w: 81, p: [["bar", [9, 9, 19, 6, 30, 8, 40, 6]], ["stem", [27, 3, 24, 13, 17, 26, 7, 31]], ["bar", [3, 22, 15, 18, 28, 17, 38, 15]], ["reach", [29, 26, 47, 27, 65, 20, 80, 20]]] },
  { w: 83, p: [["reach", [4, 11, 25, 9, 53, 11, 82, 6]], ["stem", [35, 14, 30, 20, 23, 26, 17, 29]], ["bar", [18, 29, 29, 24, 40, 26, 49, 24]], ["stem", [47, 18, 51, 22, 53, 25, 57, 29]]] },
  { w: 77, p: [["stem", [23, 4, 28, 6, 30, 9, 26, 11]], ["bar", [5, 18, 17, 14, 29, 14, 38, 12, 38, 19, 27, 25, 17, 31]], ["sweep", [36, 21, 44, 25, 56, 30, 76, 20]]] },
  { w: 79, p: [["bar", [9, 10, 21, 6, 34, 7, 43, 5, 40, 11, 32, 16, 25, 18]], ["bar", [24, 18, 34, 15, 44, 15, 51, 13]], ["stem", [46, 17, 42, 25, 35, 29, 27, 32]], ["reach", [7, 28, 31, 27, 57, 23, 78, 22]]] },
  { w: 78, p: [["stem", [11, 6, 13, 13, 18, 20, 24, 23]], ["stem", [31, 6, 28, 15, 21, 25, 14, 31]], ["reach", [3, 19, 24, 15, 51, 17, 77, 10]], ["stem", [44, 16, 46, 24, 42, 28, 34, 32]]] },
  { w: 73, p: [["stem", [15, 5, 10, 13, 12, 20, 20, 22]], ["bar", [6, 26, 16, 23, 27, 20, 35, 20]], ["reach", [28, 28, 44, 27, 61, 20, 72, 19]], ["bar", [43, 10, 48, 8, 53, 9, 56, 11]]] },
  { w: 80, p: [["reach", [3, 10, 20, 7, 45, 9, 79, 6]], ["stem", [48, 10, 44, 18, 34, 24, 26, 26]], ["bar", [14, 16, 20, 17, 23, 20, 19, 24]], ["bar", [18, 30, 28, 28, 39, 30, 50, 25]]] },
  { w: 84, p: [["bar", [5, 25, 9, 16, 16, 11, 25, 14, 31, 16, 37, 18, 45, 17]], ["stem", [29, 5, 29, 16, 25, 26, 20, 32]], ["reach", [40, 24, 53, 21, 69, 14, 83, 11]]] },
  { w: 71, p: [["bar", [7, 10, 20, 7, 34, 9, 41, 7]], ["stem", [33, 12, 31, 18, 22, 21, 14, 24]], ["bar", [10, 27, 21, 25, 33, 25, 40, 22]], ["sweep", [36, 16, 41, 26, 51, 31, 70, 20]]] },
  { w: 86, p: [["stem", [11, 7, 8, 17, 10, 24, 18, 26]], ["bar", [18, 13, 31, 10, 44, 13, 50, 10]], ["stem", [36, 8, 35, 18, 31, 26, 24, 31]], ["reach", [6, 30, 29, 30, 59, 23, 85, 15]]] },
  { w: 75, p: [["bar", [7, 8, 18, 11, 28, 6, 37, 7]], ["stem", [17, 14, 18, 19, 16, 24, 10, 27]], ["bar", [27, 15, 35, 13, 43, 14, 48, 12, 48, 17, 41, 22, 34, 25]], ["sweep", [28, 27, 39, 31, 57, 25, 74, 17]]] },
  { w: 82, p: [["reach", [4, 14, 23, 11, 53, 10, 81, 8]], ["bar", [19, 23, 29, 18, 40, 19, 48, 17]], ["stem", [30, 9, 30, 20, 24, 28, 16, 32]], ["stem", [46, 22, 50, 25, 55, 28, 62, 28]]] },
  { w: 78, p: [["bar", [6, 11, 19, 9, 35, 10, 44, 7]], ["stem", [36, 11, 33, 20, 29, 25, 19, 29]], ["bar", [12, 18, 19, 20, 25, 23, 29, 25]], ["reach", [31, 29, 47, 25, 62, 22, 77, 15]]] },
  { w: 84, p: [["stem", [12, 5, 15, 12, 15, 18, 10, 22]], ["bar", [24, 9, 35, 6, 42, 9, 48, 10, 46, 16, 40, 20, 33, 22]], ["bar", [9, 28, 20, 25, 34, 24, 44, 24]], ["reach", [47, 21, 58, 20, 70, 11, 83, 9]]] },
  { w: 72, p: [["bar", [8, 10, 21, 7, 32, 10, 42, 7]], ["stem", [29, 12, 26, 20, 17, 25, 8, 31]], ["bar", [26, 25, 35, 21, 44, 23, 51, 20]], ["sweep", [42, 26, 51, 30, 61, 24, 71, 17]]] },
  { w: 85, p: [["reach", [3, 9, 27, 7, 55, 12, 84, 6]], ["stem", [23, 13, 26, 20, 22, 28, 16, 31]], ["bar", [34, 17, 42, 14, 51, 17, 55, 14]], ["stem", [48, 20, 43, 25, 36, 28, 29, 29]], ["bar", [43, 29, 53, 29, 62, 24, 66, 22]]] },
  { w: 76, p: [["bar", [4, 14, 17, 10, 28, 11, 36, 9]], ["stem", [19, 5, 21, 14, 19, 24, 13, 29]], ["bar", [31, 16, 43, 13, 49, 15, 52, 14, 48, 21, 39, 25, 32, 27]], ["reach", [39, 29, 49, 29, 63, 22, 75, 17]]] },
  { w: 82, p: [["stem", [9, 7, 13, 11, 17, 15, 15, 20]], ["bar", [26, 7, 37, 8, 45, 6, 54, 5]], ["stem", [40, 11, 36, 20, 30, 25, 21, 28]], ["reach", [5, 31, 26, 28, 56, 27, 81, 17]]] },
  { w: 74, p: [["bar", [8, 10, 20, 9, 30, 6, 40, 7, 40, 13, 30, 18, 22, 21]], ["stem", [12, 18, 14, 23, 19, 27, 27, 28]], ["bar", [27, 20, 36, 18, 44, 19, 49, 17]], ["sweep", [36, 28, 46, 30, 62, 22, 73, 16]]] },
  { w: 86, p: [["stem", [14, 6, 11, 14, 8, 22, 5, 27]], ["reach", [21, 15, 39, 10, 63, 12, 85, 7]], ["bar", [19, 23, 30, 20, 39, 23, 47, 20]], ["stem", [40, 15, 38, 24, 33, 29, 24, 32]], ["bar", [43, 29, 55, 28, 62, 23, 66, 21]]] },
];

/** 把一条三次贝塞尔点列采样成密集点，斜切由 slant 统一施加（行书右倾）。 */
function sampleCurve(arr: number[], ox = 0, oy = 0, sx = 1, sy = 1, slant = 0): InkPoint[] {
  const pts: InkPoint[] = [];
  let x0 = arr[0];
  let y0 = arr[1];
  const point = (x: number, y: number): InkPoint => ({
    x: ox + (x + slant * (y - 22)) * sx,
    y: oy + y * sy,
    r: 0,
    grain: false,
    fiber: 0,
    d: 0,
  });
  pts.push(point(x0, y0));
  for (let k = 2; k < arr.length; k += 6) {
    const [x1, y1, x2, y2, x3, y3] = arr.slice(k, k + 6);
    const estimate =
      Math.hypot(x1 - x0, y1 - y0) + Math.hypot(x2 - x1, y2 - y1) + Math.hypot(x3 - x2, y3 - y2);
    const n = Math.max(4, Math.ceil(estimate * Math.max(sx, sy) * 1.65));
    for (let j = 1; j <= n; j += 1) {
      const t = j / n;
      const v = 1 - t;
      pts.push(
        point(
          v * v * v * x0 + 3 * v * v * t * x1 + 3 * v * t * t * x2 + t * t * t * x3,
          v * v * v * y0 + 3 * v * v * t * y1 + 3 * v * t * t * y2 + t * t * t * y3,
        ),
      );
    }
    x0 = x3;
    y0 = y3;
  }
  return pts;
}

/** 柔字：两端收笔、中段饱满，靠正弦包络做提按。 */
function softBrush(pts: InkPoint[], params: InkParams, rng: Rng): void {
  const phase = rng.next() * 6.28;
  const variation = params.pressure / 100;
  const base = params.weight * rng.range(0.83, 1.15);
  pts.forEach((p, i) => {
    const t = i / (pts.length - 1);
    const envelope = Math.pow(Math.sin(Math.PI * t), 0.4);
    const pressure =
      (1 - variation) * 0.58 +
      variation * (0.48 + 0.31 * Math.sin(t * 7 + phase) + 0.15 * Math.cos(t * 16 + phase));
    p.r = Math.max(0.08, base * envelope * pressure + 0.07);
    p.grain = Math.sin(i * 0.1 + phase) > 0.04;
    p.fiber = params.dry / 100;
  });
}

/** 锋字：每种笔势一条「压力曲线」，起笔轻、行笔重、收笔出锋。 */
const PROFILES: Record<SharpKind, [number, number][]> = {
  sweep: [[0, 0.06], [0.12, 0.55], [0.32, 1], [0.58, 0.6], [0.83, 0.18], [1, 0.008]],
  bar: [[0, 0.04], [0.16, 0.83], [0.38, 0.7], [0.72, 0.3], [1, 0.01]],
  reach: [[0, 0.03], [0.12, 0.75], [0.3, 0.58], [0.65, 0.28], [1, 0.006]],
  stem: [[0, 0.04], [0.24, 0.82], [0.48, 1], [0.73, 0.58], [1, 0.01]],
};

function interpProfile(t: number, knots: [number, number][]): number {
  for (let i = 1; i < knots.length; i += 1) {
    if (t <= knots[i][0]) {
      const a = knots[i - 1];
      const z = knots[i];
      const v = (t - a[0]) / (z[0] - a[0]);
      const e = v * v * (3 - 2 * v);
      return a[1] + (z[1] - a[1]) * e;
    }
  }
  return knots[knots.length - 1][1];
}

function sharpBrush(pts: InkPoint[], params: InkParams, kind: SharpKind, rng: Rng): void {
  const profile = PROFILES[kind];
  const mass = params.weight * (kind === "sweep" ? 0.9 : kind === "reach" ? 0.8 : kind === "stem" ? 1.03 : 0.91);
  const variation = params.pressure / 100;
  const phase = rng.next() * 6.28;
  pts.forEach((p, i) => {
    const t = i / (pts.length - 1);
    const press = interpProfile(t, profile);
    const taper = Math.min(1, t * 12, (1 - t) * 9);
    const uniform = 0.48 * Math.max(0, taper);
    p.r = Math.max(
      0.035,
      mass * ((1 - variation) * uniform + variation * press) * (1 + 0.018 * Math.sin(i * 0.8 + phase)),
    );
    p.grain = t > 0.22 && t < 0.92 && Math.sin(i * 0.17 + phase) > 0.1;
    p.fiber = params.dry / 100;
  });
}

/** 把后一笔的头接到前一笔的尾：用两端切线拉一段牵丝，并把接缝处两边的笔宽抹匀。 */
function joinPaths(a: InkPoint[], c: InkPoint[], params: InkParams): void {
  const p = a[a.length - 1];
  const q = c[0];
  const before = a[Math.max(0, a.length - 5)];
  const after = c[Math.min(c.length - 1, 4)];
  const d = Math.hypot(q.x - p.x, q.y - p.y);
  const handle = Math.min(20, d * 0.4);
  const ad = Math.hypot(p.x - before.x, p.y - before.y) || 1;
  const cd = Math.hypot(after.x - q.x, after.y - q.y) || 1;
  const bridge = sampleCurve([
    p.x,
    p.y,
    p.x + ((p.x - before.x) / ad) * handle,
    p.y + ((p.y - before.y) / ad) * handle,
    q.x - ((after.x - q.x) / cd) * handle,
    q.y - ((after.y - q.y) / cd) * handle,
    q.x,
    q.y,
  ]);
  const radius = Math.max(0.16, ((params.weight * params.linkWidth) / 100) * 0.43);
  const taper = Math.min(13, a.length - 1, c.length - 1);
  const span = Math.max(1, taper);
  for (let n = 0; n <= taper; n += 1) {
    const blend = 1 - n / span;
    a[a.length - 1 - n].r = a[a.length - 1 - n].r * (1 - blend) + radius * blend;
    c[n].r = c[n].r * (1 - blend) + radius * blend;
  }
  bridge.forEach((v, i) => {
    v.r = radius * (0.84 + 0.16 * Math.sin((i / Math.max(1, bridge.length - 1)) * Math.PI));
    v.grain = false;
    v.fiber = 0;
  });
  a.push(...bridge.slice(1), ...c.slice(1));
}

/**
 * 有状态的场景：按行懒生成，行号即书页格线的行号。
 * 每次 appendRow 都把新一行的时钟接在上一行之后，所以 total 永远是「已生成内容的终点」，
 * 调用方只要保证 total 比当前时刻更远，笔尖就永远不会写到空白处。
 */
export class InkScene {
  readonly strokes: InkStroke[] = [];
  /** 已生成的行数（= 已占用的格线行数）。 */
  rows = 0;
  /** 已生成内容的终点（毫秒）。 */
  total = 180;

  private readonly unitWidth: number;
  private readonly edition: number;
  private readonly params: InkParams = { ...INK_PARAMS };
  private clock = 180;
  private recentSoft: number[] = [];
  private recentSharp: number[] = [];

  constructor(unitWidth: number, edition = 1) {
    this.unitWidth = unitWidth;
    this.edition = edition;
  }

  /** 画布总高（单位空间）：已写行 + 底部留白，够最后一行压线不被裁。 */
  get heightUnits(): number {
    return this.rows * UNIT_LINE_GAP + TAIL_UNITS;
  }

  /**
   * 写下一行。
   * 原页最后一行只写 77% 是为了让静态图停在半途；这里没有最后一行，每行都写满右边界，
   * 否则每四行会凭空断一截。
   */
  appendRow(): void {
    const row = this.rows;
    const left = this.unitWidth < 700 ? 39 : 58;
    const right = this.unitWidth - (this.unitWidth < 700 ? 44 : 62);
    const rowStrokes: InkStroke[] = [];
    let x = left;
    let j = 0;

    while (x + 45 < right) {
      // 每个字一个固定种子：行与行可以独立生成，重排也只换内容不换性格
      const rng = new Rng((7319 + this.edition * 93517 + row * 31271 + j * 6791) >>> 0);
      let soft = Math.floor(rng.next() * FORMS.length);
      let sharp = Math.floor(rng.next() * GLYPHS.length);
      while (this.recentSoft.includes(soft)) soft = (soft + 1) % FORMS.length;
      while (this.recentSharp.includes(sharp)) sharp = (sharp + 7) % GLYPHS.length;
      this.recentSoft.push(soft);
      this.recentSharp.push(sharp);
      if (this.recentSoft.length > 6) this.recentSoft.shift();
      if (this.recentSharp.length > 8) this.recentSharp.shift();

      const pick = (j * 0.61803398875 + row * 0.381966 + this.edition * 0.173) % 1;
      const isSharp = pick < this.params.sharpness / 100;
      const sx = rng.range(0.88, 1.03);
      const sy = rng.range(0.86, 1.06);
      const slant = rng.range(-0.17, -0.03);
      const oy = 19 + row * UNIT_LINE_GAP + rng.range(-1, 1) * this.params.sway * 0.1;
      const group = row * 100 + j;

      const items: InkStroke[] = isSharp
        ? this.sharpGlyph(sharp, x, oy, sx, sy, row, group, rng)
        : this.softGlyph(soft, x, oy, sx, sy, slant, row, group, rng);

      for (const item of items) {
        const last = rowStrokes[rowStrokes.length - 1];
        const cross = last !== undefined && last.group !== group;
        const linked =
          last !== undefined &&
          rng.next() < this.params.link / 100 &&
          (!cross || item.pts[0].x - last.pts[last.pts.length - 1].x < 35);
        if (last !== undefined && linked) joinPaths(last.pts, item.pts, this.params);
        else rowStrokes.push(item);
      }

      x += this.params.spacing;
      j += 1;
    }

    rowStrokes.forEach((stroke, index) => {
      let d = 0;
      stroke.pts.forEach((p, k) => {
        if (k > 0) d += Math.hypot(p.x - stroke.pts[k - 1].x, p.y - stroke.pts[k - 1].y);
        p.d = d;
      });
      stroke.length = d;
      stroke.start = this.clock;
      stroke.duration = 45 + d * 3.2;
      const next = rowStrokes[index + 1];
      this.clock =
        stroke.start + stroke.duration + (next ? 80 * (1 - this.params.link / 100) + 15 : ROW_GAP);
    });

    this.total = this.clock;
    this.rows = row + 1;
    this.strokes.push(...rowStrokes);
  }

  private softGlyph(
    index: number,
    x: number,
    oy: number,
    sx: number,
    sy: number,
    slant: number,
    row: number,
    group: number,
    rng: Rng,
  ): InkStroke[] {
    return FORMS[index].map((path) => {
      const pts = sampleCurve(path, x, oy, sx, sy, slant);
      softBrush(pts, this.params, rng);
      return { pts, line: row, group, start: 0, duration: 0, length: 0 };
    });
  }

  private sharpGlyph(
    index: number,
    x: number,
    oy: number,
    sx: number,
    sy: number,
    row: number,
    group: number,
    rng: Rng,
  ): InkStroke[] {
    const glyph = GLYPHS[index];
    const params: InkParams = { ...this.params, weight: this.params.weight * 0.82 };
    return glyph.p.map(([kind, path]) => {
      const pts = sampleCurve(path, x, oy + 6, (46 / glyph.w) * sx, 1.12 * sy, 0);
      // 锋字整体右高左低，像笔尖在格线内往上挑
      for (const p of pts) p.y -= (p.x - x) * 0.085;
      sharpBrush(pts, params, kind, rng);
      return { pts, line: row, group, start: 0, duration: 0, length: 0 };
    });
  }
}

/**
 * 画一笔的第 i 段：把相邻两点的半径连成梯形，再补一个圆头，
 * 于是笔宽逐点变化就变成了提按。飞白用 destination-out 擦，不能画纸色——
 * 画布是透明的，涂纸色会在纸纹上糊出一层。
 */
export function drawSegment(ctx: CanvasRenderingContext2D, stroke: InkStroke, i: number, ink: string): void {
  const a = stroke.pts[i - 1];
  const c = stroke.pts[i];
  const dx = c.x - a.x;
  const dy = c.y - a.y;
  const len = Math.hypot(dx, dy);
  if (len < 0.0001) return;
  const nx = -dy / len;
  const ny = dx / len;
  ctx.fillStyle = ink;
  ctx.beginPath();
  ctx.moveTo(a.x + nx * a.r, a.y + ny * a.r);
  ctx.lineTo(c.x + nx * c.r, c.y + ny * c.r);
  ctx.lineTo(c.x - nx * c.r, c.y - ny * c.r);
  ctx.lineTo(a.x - nx * a.r, a.y - ny * a.r);
  ctx.closePath();
  ctx.fill();
  ctx.beginPath();
  ctx.ellipse(c.x, c.y, c.r, c.r * 0.88, Math.atan2(dy, dx), 0, Math.PI * 2);
  ctx.fill();
  if (c.grain && c.r > 0.7 && c.fiber > 0) {
    ctx.globalAlpha = c.fiber * 0.8;
    ctx.globalCompositeOperation = "destination-out";
    ctx.lineWidth = 0.25 + c.fiber * 0.35;
    ctx.beginPath();
    ctx.moveTo(a.x + nx * a.r * 0.24, a.y + ny * a.r * 0.24);
    ctx.lineTo(c.x + nx * c.r * 0.24, c.y + ny * c.r * 0.24);
    ctx.stroke();
    ctx.globalCompositeOperation = "source-over";
    ctx.globalAlpha = 1;
  }
}
