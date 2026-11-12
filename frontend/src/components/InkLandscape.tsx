import { useEffect, useRef } from "react";

/* ============================================================
   墨色山水 · 全站底景
   移植自 design-lab/ink/jianghu-ink-atelier.html（「一苇江湖 ·
   水墨调景台」）的 canvas 绘制：宣纸上淡墨远山、缓流江水与条带
   倒影、山脚薄雾、斗笠孤舟。
   只取画面，原页的调参台、题字与卡片版式一概不入站内；参数按默认
   预设「江天开阔」固化在 LANDSCAPE，改观感请去调参台拖滑杆再抄回来
   （见 design-lab/ink/README.md）。
   纸纹不在这里画：由 CSS 的 feTurbulence 层合成（.site-ink-paper），
   省掉每帧一次全屏填充；画稿本身也是模块级单例，见 getArtwork()。
   ============================================================ */

/** 山体的画幅：一切按 1600×1000 画好，再按屏幕「裁看」（cover），山形在任何视口一致 */
const W = 1600;
const H = 1000;

/** 与调参台同名同义，单位一致（百分比 / %） */
const LANDSCAPE = {
  horizon: 73,
  height: 29,
  ink: 60,
  bleed: 60,
  fog: 48,
  water: 62,
  speed: 40,
  boatX: 73,
  boatY: 85,
  boatSize: 100,
} as const;

const rng = (seed: number) => {
  let s = seed | 0;
  return () => {
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
};

const noise = (x: number, s = 0) =>
  Math.sin(x * 1.71 + s) * 0.52 +
  Math.sin(x * 3.79 + s * 2) * 0.25 +
  Math.sin(x * 9.27 + s * 4) * 0.14 +
  Math.sin(x * 22.71 + s) * 0.09;

type Pt = [number, number];
/** 山脊的一个峰：横向位置 / 峰高 / 峰宽（都是 0-1 的比例） */
type Peak = [number, number, number];

const tracePath = (g: CanvasRenderingContext2D, pts: Pt[]) => {
  g.beginPath();
  pts.forEach((p, i) => (i ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1])));
  g.closePath();
};

/** 远山三层：每层先沿脊线画淡墨晕，再上主 wash、墨点、干笔脉，最后向下淡出 */
const LAYERS = [
  {
    a: 0.16, k: 0.77, off: -32, seed: 37,
    peaks: [[0.02, 0.8, 0.12], [0.22, 0.68, 0.1], [0.43, 0.5, 0.065], [0.67, 0.92, 0.09], [0.87, 0.98, 0.12], [1.05, 0.7, 0.09]] as Peak[],
  },
  {
    a: 0.24, k: 0.81, off: -9, seed: 76,
    peaks: [[-0.04, 0.75, 0.1], [0.13, 0.91, 0.075], [0.29, 0.4, 0.08], [0.79, 0.9, 0.105], [0.99, 0.65, 0.13]] as Peak[],
  },
  {
    a: 0.43, k: 0.82, off: 13, seed: 124,
    peaks: [[-0.04, 0.8, 0.16], [0.11, 0.64, 0.08], [0.25, 0.19, 0.08], [0.76, 0.94, 0.09], [0.91, 0.25, 0.12], [1.03, 0.65, 0.11]] as Peak[],
  },
];

/** 舟与人的剪影：同一支笔沿骨架叠墨，不做几何拼贴 */
const BOAT_BODY: Pt[] = [[58, 168], [80, 179], [112, 186], [177, 190], [242, 188], [306, 177], [348, 158], [338, 178], [307, 193], [256, 204], [182, 209], [123, 202], [87, 190], [69, 181]];
const FIGURE: Pt[][] = [
  [[207, 127], [200, 139], [197, 157], [185, 171], [220, 176], [230, 170], [216, 152], [216, 137]],
  [[205, 117], [212, 117], [215, 125], [210, 132], [204, 128]],
  [[191, 122], [207, 109], [228, 124], [211, 127]],
  [[214, 138], [224, 152], [242, 155], [243, 160], [220, 157], [207, 146]],
];

/** 远山：三层各自成形后叠进一张画布，最后整体向下淡出，让山脚融进纸里 */
function paintMountains() {
  const mount = document.createElement("canvas");
  mount.width = W;
  mount.height = H;
  const mc = mount.getContext("2d")!;
  const base = (LANDSCAPE.horizon / 100) * H;
  const amp = (LANDSCAPE.height / 100) * H;
  const ink = LANDSCAPE.ink / 100;

  for (const layer of LAYERS) {
    const temp = document.createElement("canvas");
    temp.width = W;
    temp.height = H;
    const g = temp.getContext("2d")!;
    const rand = rng(layer.seed);
    const ridge: Pt[] = [];
    for (let x = -20; x <= W + 20; x += 4) {
      const u = x / W;
      let v = 0;
      for (const [px, py, pw] of layer.peaks) v += py * Math.exp(-(((u - px) / pw) ** 2) * 1.4);
      v *= layer.k;
      const rock = noise(u * 39, layer.seed) * 0.022 + noise(u * 117, layer.seed) * 0.005;
      ridge.push([x, base + layer.off - amp * Math.max(0, v + rock * Math.min(1, v * 5))]);
    }
    const poly: Pt[] = [...ridge, [W + 20, base + 70], [-20, base + 70]];

    // 纸缘淡墨：同一条轮廓错开叠十几次，模拟宣纸吃墨的毛边
    for (let j = 0; j < 12; j++) {
      g.save();
      g.filter = j === 0 ? `blur(${1 + (LANDSCAPE.bleed / 100) * 4}px)` : "none";
      g.translate((rand() - 0.5) * LANDSCAPE.bleed * 0.09, (rand() - 0.5) * LANDSCAPE.bleed * 0.055);
      tracePath(g, poly);
      g.fillStyle = `rgba(70,72,65,${layer.a * ink * 0.08})`;
      g.fill();
      g.restore();
    }

    g.save();
    tracePath(g, poly);
    g.clip();
    const wash = g.createLinearGradient(0, base - amp, 0, base + 28);
    wash.addColorStop(0, `rgba(61,64,57,${layer.a * ink * 0.7})`);
    wash.addColorStop(0.6, `rgba(84,86,76,${layer.a * ink * 0.75})`);
    wash.addColorStop(1, "rgba(132,132,117,0)");
    g.fillStyle = wash;
    g.fillRect(0, base - amp * 1.5, W, amp * 2);

    // 墨点：一半提亮一半吃墨，山体因此不是一块平涂
    for (let i = 0; i < 420; i++) {
      const x = rand() * W;
      const y = base - amp + rand() * amp * 1.2;
      const r = 4 + rand() * 29;
      g.save();
      g.translate(x, y);
      g.rotate(-0.4 + rand() * 0.8);
      g.scale(0.3 + rand() * 0.9, 1);
      const grad = g.createRadialGradient(0, 0, 0, 0, 0, r);
      grad.addColorStop(0, `rgba(${rand() > 0.6 ? "237,234,218" : "53,57,48"},${(0.02 + rand() * 0.06) * ink})`);
      grad.addColorStop(1, "rgba(61,65,56,0)");
      g.fillStyle = grad;
      g.fillRect(-r, -r, r * 2, r * 2);
      g.restore();
    }

    // 干笔脉：把大块 wash 拆成山石纹理
    for (let j = 0; j < 110; j++) {
      const x = rand() * W;
      const idx = Math.min(ridge.length - 1, Math.max(0, Math.floor((x + 20) / 4)));
      const y = ridge[idx][1];
      g.beginPath();
      g.moveTo(x, y + rand() * 20);
      g.bezierCurveTo(x - 9, y + amp * 0.12, x + 25, base - amp * 0.09, x + 40 + rand() * 55, base + 15);
      g.strokeStyle = `rgba(49,54,46,${(0.01 + rand() * 0.022) * ink})`;
      g.lineWidth = 0.3 + rand() * 1.7;
      g.stroke();
    }

    for (let i = 0; i < 2600; i++) {
      g.fillStyle = `rgba(245,240,223,${rand() * 0.1})`;
      g.fillRect(rand() * W, base - amp + rand() * amp * 1.2, 0.5 + rand() * 1.6, 0.4 + rand() * 1.5);
    }
    g.restore();

    g.globalCompositeOperation = "destination-in";
    const fade = g.createLinearGradient(0, base - amp * 0.18, 0, base + 45);
    fade.addColorStop(0, "#000");
    fade.addColorStop(1, "transparent");
    g.fillStyle = fade;
    g.fillRect(0, 0, W, H);
    g.globalCompositeOperation = "source-over";

    mc.drawImage(temp, 0, 0);
  }
  return mount;
}

/** 孤舟：斗笠独坐。船体横向一笔定形，人下半身藏在船舷后 */
function paintBoat() {
  const boat = document.createElement("canvas");
  boat.width = 420;
  boat.height = 230;
  const g = boat.getContext("2d")!;
  const rand = rng(18);
  const wash = (pts: Pt[], opacity = 1) => {
    for (let i = 0; i < 8; i++) {
      g.save();
      g.translate((rand() - 0.5) * 1.8, (rand() - 0.5) * 1.5);
      g.filter = i < 2 ? "blur(1.1px)" : "none";
      tracePath(g, pts);
      g.fillStyle = `rgba(43,48,39,${0.24 * opacity})`;
      g.fill();
      g.restore();
    }
  };
  for (const shape of FIGURE) wash(shape, shape === FIGURE[3] ? 0.85 : 1);
  g.strokeStyle = "rgba(56,63,48,.6)";
  g.lineWidth = 0.8;
  g.beginPath();
  g.moveTo(241, 155);
  g.quadraticCurveTo(297, 114, 334, 159);
  g.stroke();
  g.strokeStyle = "rgba(56,63,48,.28)";
  g.beginPath();
  g.moveTo(334, 159);
  g.lineTo(340, 201);
  g.stroke();

  wash(BOAT_BODY, 1);
  g.strokeStyle = "rgba(32,38,30,.8)";
  g.lineWidth = 2;
  g.beginPath();
  g.moveTo(63, 168);
  g.bezierCurveTo(133, 198, 276, 193, 347, 158);
  g.stroke();
  g.strokeStyle = "rgba(238,230,203,.4)";
  g.lineWidth = 1;
  g.beginPath();
  g.moveTo(111, 192);
  g.quadraticCurveTo(210, 209, 308, 184);
  g.stroke();
  g.strokeStyle = "rgba(61,63,50,.7)";
  g.lineWidth = 2;
  g.beginPath();
  g.moveTo(142, 183);
  g.lineTo(135, 164);
  g.stroke();
  return boat;
}

/* 画稿与视口无关、参数固定：全站只生成一次。
   路由来回切换、组件反复挂载都直接复用这张画布，不再重算墨点——这正是
   「每次回首页卡一下」的根因（原先每次挂载要同步跑 5 万多次 canvas 调用）。 */
let shared: { mount: HTMLCanvasElement; boat: HTMLCanvasElement } | null = null;
const getArtwork = () => (shared ??= { mount: paintMountains(), boat: paintBoat() });

class Landscape {
  canvas: HTMLCanvasElement;
  ctx!: CanvasRenderingContext2D;
  w = 1;
  h = 1;
  /** 画幅到屏幕的等比缩放（cover），resize 时现算 */
  scale = 1;
  clock = 0;
  mount: HTMLCanvasElement;
  boat: HTMLCanvasElement;
  flat = document.createElement("canvas");

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas;
    const art = getArtwork();
    this.mount = art.mount;
    this.boat = art.boat;
    this.resize();
  }

  resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 1.7);
    const r = this.canvas.getBoundingClientRect();
    this.w = Math.max(1, r.width);
    this.h = Math.max(1, r.height);
    this.canvas.width = Math.round(this.w * dpr);
    this.canvas.height = Math.round(this.h * dpr);
    this.ctx = this.canvas.getContext("2d")!;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    // 等比放大到铺满屏幕（cover），超出的部分居中裁掉、底边对齐：
    // 窄高屏看到的是画的中段，山仍是同一副模样，不会拉成尖峰。
    this.scale = Math.max(this.w / W, this.h / H);
    // 按屏幕尺寸预缩一份远山：每帧 1:1 贴图，省掉全屏缩放
    this.flat.width = Math.round(this.w * dpr);
    this.flat.height = Math.round(this.h * dpr);
    const fc = this.flat.getContext("2d")!;
    fc.setTransform(dpr, 0, 0, dpr, 0, 0);
    fc.drawImage(this.mount, (this.w - W * this.scale) / 2, this.h - H * this.scale, W * this.scale, H * this.scale);
  }

  advance(dt: number) {
    this.clock += dt * (LANDSCAPE.speed / 40);
  }

  draw(t: number) {
    const c = this.ctx;
    const w = this.w;
    const h = this.h;
    c.clearRect(0, 0, w, h);

    const s = this.scale;
    const offX = (w - W * s) / 2; // 画幅比屏幕宽时居中裁，比屏幕窄时留负值
    const offY = h - H * s; // 底边对齐：水岸始终压在屏幕下缘
    const horizonPx = (LANDSCAPE.horizon / 100) * H;
    const waterline = offY + horizonPx * s;
    const flow = t;

    // 水面淡墨：江心留空，越往近岸越沉
    const waterwash = c.createLinearGradient(0, waterline, 0, h);
    waterwash.addColorStop(0, "rgba(128,139,115,0)");
    waterwash.addColorStop(0.25, `rgba(128,139,115,${0.025 + LANDSCAPE.water * 0.0003})`);
    waterwash.addColorStop(1, `rgba(110,125,107,${0.035 + LANDSCAPE.water * 0.0005})`);
    c.fillStyle = waterwash;
    c.fillRect(0, waterline, w, h - waterline);

    // 倒影：远山的窄条逐行错位、随流水抽动
    c.save();
    c.globalAlpha = (0.16 * LANDSCAPE.water) / 100;
    for (let y = 0; y < Math.min(H * 0.28, H - horizonPx); y += 3) {
      const sourceY = horizonPx - y * 1.25;
      if (sourceY < 0) break;
      const shift = Math.sin(y * 0.087 + flow * 0.36) * (1 + y * 0.015) * (LANDSCAPE.water / 40);
      c.drawImage(this.mount, 0, sourceY, W, 3, offX + shift * s, offY + (horizonPx + y) * s, W * s, 3.6 * s);
    }
    c.restore();
    c.drawImage(this.flat, 0, 0, w, h);

    // 山脚薄雾：五团横向游移，山与水的接缝因此不至于生硬
    const fog = LANDSCAPE.fog / 100;
    c.save();
    for (let i = 0; i < 5; i++) {
      const x = w * (i * 0.29 - 0.08) + Math.sin(t * 0.055 + i * 2) * w * 0.055;
      const y = waterline - h * 0.012 + Math.sin(t * 0.13 + i) * h * 0.012;
      c.save();
      c.translate(x, y);
      c.scale(1, 0.12);
      const r = w * 0.31;
      const g = c.createRadialGradient(0, 0, 0, 0, 0, r);
      g.addColorStop(0, `rgba(245,241,229,${fog * (0.29 + 0.07 * Math.sin(t * 0.12 + i))})`);
      g.addColorStop(1, "rgba(245,241,229,0)");
      c.fillStyle = g;
      c.fillRect(-r, -r, r * 2, r * 2);
      c.restore();
    }
    c.restore();

    // 水纹：细长横笔，随流轻摆
    const rand = rng(91);
    for (let i = 0; i < 115; i++) {
      const x = rand() * w;
      const y = waterline + rand() * (h - waterline);
      const len = (7 + rand() * 100) * s;
      const phase = rand() * 6.28;
      const sway = Math.sin(flow * 0.27 + phase) * 9 * s;
      const alpha = ((0.013 + rand() * 0.045) * LANDSCAPE.water) / 60;
      c.strokeStyle = `rgba(80,97,77,${alpha})`;
      c.lineWidth = 0.5;
      c.beginPath();
      c.moveTo(x + sway, y);
      c.bezierCurveTo(x + len * 0.3 + sway, y - 0.5, x + len * 0.7 + sway, y + 0.5, x + len + sway, y);
      c.stroke();
    }

    // 孤舟：原处轻摇；倒影与三圈水纹跟着船走。
    // 尺寸跟画幅缩放，但要封顶在屏宽 24%——竖屏（cover 后 scale 接近 1）里
    // 不封顶会让一叶小舟变成占掉半屏的大船。
    const bob = Math.sin(t * 0.83) * 1.7;
    const bs = Math.min(Math.min(1.1, Math.max(0.42, s)) * 0.53 * (LANDSCAPE.boatSize / 100), (w * 0.24) / 420);
    const bx = (w * LANDSCAPE.boatX) / 100;
    const by = Math.max(waterline + 20, (h * LANDSCAPE.boatY) / 100) + bob;
    c.save();
    c.translate(bx, by);
    c.rotate(Math.sin(t * 0.61) * 0.009);
    c.drawImage(this.boat, -210 * bs, -202 * bs, 420 * bs, 230 * bs);
    c.restore();

    c.save();
    c.globalAlpha = (0.18 * LANDSCAPE.water) / 100;
    for (let y = 0; y < 90; y += 3) {
      const shift = Math.sin(y * 0.25 + flow * 0.75) * 2.3;
      c.drawImage(this.boat, 0, 202 - y, 420, 3, bx - 210 * bs + shift, by + y * bs * 0.63, 420 * bs, 3 * bs * 0.8);
    }
    c.restore();

    c.save();
    c.translate(bx, by + 7 * bs);
    c.scale(1, 0.16);
    for (let i = 0; i < 3; i++) {
      const radius = (80 + i * 27 + Math.sin(flow * 0.4 + i) * 5) * bs;
      c.beginPath();
      c.ellipse(0, i * 5, radius, 25 + i * 9, 0, 0, Math.PI * 2);
      c.strokeStyle = `rgba(82,95,74,${((0.12 - i * 0.025) * LANDSCAPE.water) / 70})`;
      c.lineWidth = 0.8;
      c.stroke();
    }
    c.restore();
  }
}

export default function InkLandscape() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const scene = new Landscape(canvas);
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
    // 缓流不需要 60fps：30fps 省一半合成，肉眼无差
    if (reduce.matches) {
      scene.draw(0);
      return () => {};
    }

    let raf = 0;
    let last = 0;
    let dead = false;
    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      if (!last) {
        last = now;
        return;
      }
      if (now - last < 32) return;
      scene.advance(Math.min(0.08, (now - last) / 1000));
      last = now;
      scene.draw(scene.clock);
    };
    const start = () => {
      last = 0;
      raf = requestAnimationFrame(frame);
    };
    const onVisible = () => {
      if (document.hidden) cancelAnimationFrame(raf);
      else if (!dead) start();
    };
    document.addEventListener("visibilitychange", onVisible);

    let resizeTimer = 0;
    const observer = new ResizeObserver(() => {
      clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(() => scene.resize(), 140);
    });
    observer.observe(canvas);

    start();
    return () => {
      dead = true;
      cancelAnimationFrame(raf);
      observer.disconnect();
      clearTimeout(resizeTimer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  return (
    <>
      <canvas ref={ref} className="site-ink" aria-hidden="true" />
      {/* 纸纤维压在所有墨之上，山水与站点内容同在一张纸上 */}
      <div className="site-ink-paper" aria-hidden="true" />
    </>
  );
}
