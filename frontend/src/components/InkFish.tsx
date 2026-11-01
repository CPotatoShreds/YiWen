import { useEffect, useRef } from "react";

/* ============================================================
   墨色游鱼 · 首页全屏水域
   算法移植自 web-frontend/ynfight-home/assets/ink.js 的 Koi/Pond
   （boids 三力 flocking + 椭圆链截面鱼身：前 1/6 增粗、其余线性
   收细、alpha 随索引渐隐；出处 unicar CodePen LwbRbo / FishPond）。
   本地化：墨色鱼、全屏水域、随机涟漪 + 点击涟漪（同心多圈全屏
   扩散反弹渐隐）、指针避让走 window 监听（画布本身
   pointer-events:none，不挡内容点击）。
   ============================================================ */

const TAU = Math.PI * 2;
const rand = (a: number, b: number) => a + Math.random() * (b - a);

interface Pt { x: number; y: number; }

/* 墨色系：同一 --ink 的深浅层次（暖炭黑 → 淡墨） */
const INK_FISH_COLORS = ["#2f2b26", "#3a352e", "#262219", "#443e35"];

/* ---------- 自发小涟漪（每隔几秒随机荡一圈，淡墨细线） ---------- */
class Ripple {
  rx: number; ry: number;
  size: number;
  life: number;
  sizeStep: number;
  lifeStep: number;
  constructor(x: number, y: number, s = 1) {
    this.rx = x; this.ry = y;
    this.size = rand(18, 40) * s;
    this.life = 200;
    this.sizeStep = rand(0.8, 1.6) * s;
    this.lifeStep = rand(1.5, 4);
  }
  step() { this.size += this.sizeStep; this.life -= this.lifeStep; }
  draw(ctx: CanvasRenderingContext2D) {
    const a = Math.max(0, Math.min(1, this.life / 200));
    ctx.lineWidth = 1;
    ctx.strokeStyle = `rgba(47,43,38,${(a * 0.14).toFixed(3)})`;
    ctx.beginPath();
    ctx.arc(this.rx, this.ry, this.size / 2, 0, TAU);
    ctx.stroke();
  }
}

/* ---------- 点击涟漪：随机 2-3 圈同心 ----------
   每圈先 easeOut 冲到全屏（到最远角），随后反弹折返——
   圆弧从屏缘收回来，返程中逐渐稀释消失。
   注：圆半径一旦超过最远角距离就整圆离屏，所以「扩散过头再
   缩回 6%」不可见；真反弹 = 出程到全屏、回程收回来。 */
const easeOutCubic = (t: number) => 1 - (1 - t) ** 3;
const smooth = (t: number) => (t <= 0 ? 0 : t >= 1 ? 1 : t * t * (3 - 2 * t));

class BigRipple {
  rx: number; ry: number;
  rmax: number;
  rings: { delay: number; scale: number; peak: number }[];
  age = 0;
  span = 240;        // 单圈生命周期（60 步/秒的帧数，约 4s）
  constructor(x: number, y: number, w: number, h: number) {
    this.rx = x; this.ry = y;
    // 全屏半径：到最远角的距离
    this.rmax = Math.hypot(Math.max(x, w - x), Math.max(y, h - y));
    const n = Math.random() < 0.5 ? 2 : 3;
    this.rings = Array.from({ length: n }, (_, i) => ({
      delay: i * rand(18, 26),
      scale: rand(0.94, 1.0),
      peak: rand(0.34, 0.44) / (i * 0.5 + 1), // 越外的圈越淡
    }));
  }
  step() { this.age++; }
  done() { return this.age > this.span + (this.rings.length - 1) * 26; }
  draw(ctx: CanvasRenderingContext2D) {
    ctx.lineWidth = 1;
    for (let i = 0; i < this.rings.length; i++) {
      const ring = this.rings[i];
      const t = (this.age - ring.delay) / this.span;
      if (t <= 0) continue;
      const k = Math.min(1, t);
      // 半径：前 40% 冲到全屏，之后反弹折返收回到 12%
      const out = easeOutCubic(Math.min(k / 0.4, 1));
      const back = smooth(Math.max((k - 0.4) / 0.5, 0)) * 0.88;
      const r = this.rmax * ring.scale * (out - back);
      // 浓淡：快速浮现 → 扩散稀释 → 返程后段渐隐至无
      const fadeIn = smooth(Math.min(k / 0.06, 1));
      const fadeOut = 1 - smooth(Math.max((k - 0.6) / 0.38, 0));
      const dilute = 1 - 0.3 * out; // 水墨扩散越远越淡
      const a = Math.max(0, fadeIn * fadeOut * dilute * ring.peak);
      if (a < 0.004) continue;
      ctx.strokeStyle = `rgba(47,43,38,${a.toFixed(3)})`;
      ctx.beginPath();
      ctx.arc(this.rx, this.ry, Math.max(0, r), 0, TAU);
      ctx.stroke();
    }
  }
}

/* ---------- 墨鱼（boids 三力 + 避指针 + 随机游动） ---------- */
interface PondOpts {
  minSpeed: number;
  maxSpeed: number; maxForce: number; perception: number;
  alignAmp: number; cohesionAmp: number; separationAmp: number;
  pointerRadius: number;
  fishScale: number;
  alpha: number;
}

class Koi {
  pond: Pond;
  color: string;
  position: Pt;
  velocity: Pt;
  acceleration: Pt = { x: 0, y: 0 };
  baseSize: number;
  bodyLength: number;
  body: Pt[];
  constructor(x: number, y: number, color: string, pond: Pond) {
    this.pond = pond;
    this.color = color;
    this.position = { x: x + rand(-60, 60), y: y + rand(-40, 40) };
    const a = rand(0, TAU), m = rand(1.2, 4);
    this.velocity = { x: Math.cos(a) * m, y: Math.sin(a) * m };
    this.baseSize = Math.floor(rand(11, 19));
    this.bodyLength = this.baseSize * (Math.random() < 0.5 ? 2 : 3);
    this.body = Array.from({ length: this.bodyLength }, () => ({ ...this.position }));
  }
  steer(others: Koi[], type: 0 | 1 | 2): Pt {
    const o = this.pond.o, p = this.position;
    let sx = 0, sy = 0, total = 0;
    for (const other of others) {
      if (other === this) continue;
      const dx = other.position.x - p.x, dy = other.position.y - p.y;
      const d = Math.hypot(dx, dy);
      if (d < o.perception) {
        if (type === 0) { sx += other.velocity.x; sy += other.velocity.y; }
        else if (type === 1) { sx += other.position.x; sy += other.position.y; }
        else { sx += (p.x - other.position.x) / (d || 1); sy += (p.y - other.position.y) / (d || 1); }
        total++;
      }
    }
    if (total > 0) {
      sx /= total; sy /= total;
      if (type === 1) { sx -= p.x; sy -= p.y; }
      let m = Math.hypot(sx, sy);
      if (m > 0) { sx = (sx / m) * o.maxSpeed; sy = (sy / m) * o.maxSpeed; }
      sx -= this.velocity.x; sy -= this.velocity.y;
      m = Math.hypot(sx, sy);
      if (m > o.maxForce) { sx = (sx / m) * o.maxForce; sy = (sy / m) * o.maxForce; }
    }
    return { x: sx, y: sy };
  }
  avoid(px: number, py: number): Pt {
    const o = this.pond.o, p = this.position;
    const dx = p.x - px, dy = p.y - py;
    const d = Math.hypot(dx, dy);
    let sx = 0, sy = 0;
    if (d < o.pointerRadius) {
      sx = dx / (d || 1); sy = dy / (d || 1);
      let m = Math.hypot(sx, sy);
      sx = (sx / m) * o.maxSpeed - this.velocity.x;
      sy = (sy / m) * o.maxSpeed - this.velocity.y;
      m = Math.hypot(sx, sy);
      if (m > o.maxForce) { sx = (sx / m) * o.maxForce; sy = (sy / m) * o.maxForce; }
    }
    return { x: sx, y: sy };
  }
  flock() {
    const o = this.pond.o, kois = this.pond.fish;
    this.acceleration.x = 0; this.acceleration.y = 0;
    const al = this.steer(kois, 0), co = this.steer(kois, 1), se = this.steer(kois, 2);
    this.acceleration.x += se.x * o.separationAmp + al.x * o.alignAmp + co.x * o.cohesionAmp;
    this.acceleration.y += se.y * o.separationAmp + al.y * o.alignAmp + co.y * o.cohesionAmp;
    const m = this.pond.pointer;
    if (m.active) {
      const av = this.avoid(m.x, m.y);
      this.acceleration.x += av.x; this.acceleration.y += av.y;
    }
    const a = rand(0, TAU); // 随机游动
    this.acceleration.x += Math.cos(a) * 0.05;
    this.acceleration.y += Math.sin(a) * 0.05;
  }
  step() {
    const o = this.pond.o, p = this.position;
    this.flock();
    // 全屏软边界：靠近边缘徐徐转向内
    const pad = 60;
    if (p.x < pad) this.acceleration.x += (pad - p.x) * 0.012;
    if (p.x > this.pond.w - pad) this.acceleration.x -= (p.x - (this.pond.w - pad)) * 0.012;
    if (p.y < pad) this.acceleration.y += (pad - p.y) * 0.012;
    if (p.y > this.pond.h - pad) this.acceleration.y -= (p.y - (this.pond.h - pad)) * 0.012;
    p.x += this.velocity.x; p.y += this.velocity.y;
    this.velocity.x += this.acceleration.x; this.velocity.y += this.acceleration.y;
    const ms = o.maxSpeed, vm = Math.hypot(this.velocity.x, this.velocity.y);
    if (vm > ms) { this.velocity.x = (this.velocity.x / vm) * ms; this.velocity.y = (this.velocity.y / vm) * ms; }
    // 最低游速兜底：转向力互相抵消会让个别鱼失速停滞，
    // 鱼身链节随即堆叠缩成一团；低于下限就沿当前航向拉回。
    const mn = o.minSpeed, v2 = Math.hypot(this.velocity.x, this.velocity.y);
    if (v2 < mn) {
      const ang = v2 < 1e-4 ? rand(0, TAU) : Math.atan2(this.velocity.y, this.velocity.x);
      this.velocity.x = Math.cos(ang) * mn;
      this.velocity.y = Math.sin(ang) * mn;
    }
    this.body.pop();
    this.body.unshift({ ...p });
  }
  drawBody(ctx: CanvasRenderingContext2D, shadow: boolean, shadowOff: number) {
    const o = this.pond.o;
    for (let index = 0; index < this.bodyLength; index++) {
      const b = this.body[index];
      let size: number;
      if (index < this.bodyLength / 6) size = this.baseSize + index * 1.8;
      else size = (shadow ? this.baseSize * 1.8 : this.baseSize * 2) - index;
      // 墨色在纸底上要够浓才可见：头部实墨，向尾部渐淡（原版亮色锦鲤的 /255 渐隐在纸底不可见）
      ctx.globalAlpha = shadow ? 0.05 : Math.max(0.06, 1 - index / this.bodyLength) * o.alpha;
      ctx.fillStyle = shadow ? "rgb(120,110,95)" : this.color;
      const rr = Math.max(0.15, (size * o.fishScale) / 2);
      ctx.beginPath();
      ctx.ellipse(b.x + (shadow ? shadowOff : 0), b.y + (shadow ? shadowOff : 0), rr, rr, 0, 0, TAU);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }
}

/* ---------- 小池 ---------- */
class Pond {
  canvas: HTMLCanvasElement;
  ctx!: CanvasRenderingContext2D;
  w = 0; h = 0;
  o: PondOpts;
  fish: Koi[] = [];
  ripples: (Ripple | BigRipple)[] = [];
  frame = 0;
  pointer = { x: -9e3, y: -9e3, active: false };

  constructor(canvas: HTMLCanvasElement, count: number, o: Partial<PondOpts> = {}) {
    this.canvas = canvas;
    this.o = {
      minSpeed: 1.6,
      maxSpeed: 3.2, maxForce: 0.09, perception: 110,
      alignAmp: 1.1, cohesionAmp: 0.85, separationAmp: 1.2,
      pointerRadius: 80, fishScale: 1.0, alpha: 0.62,
      ...o,
    };
    this.resize();
    for (let i = 0; i < count; i++) {
      this.fish.push(new Koi(this.w * 0.5, this.h * 0.5, INK_FISH_COLORS[i % INK_FISH_COLORS.length], this));
    }
  }
  resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const r = this.canvas.getBoundingClientRect();
    this.canvas.width = Math.max(1, Math.round(r.width * dpr));
    this.canvas.height = Math.max(1, Math.round(r.height * dpr));
    this.ctx = this.canvas.getContext("2d")!;
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.w = r.width; this.h = r.height;
  }
  step() {
    this.frame++;
    if (this.frame % 140 === 0) this.ripples.push(new Ripple(rand(60, this.w - 60), rand(60, this.h - 60)));
    for (const k of this.fish) k.step();
    for (let i = this.ripples.length - 1; i >= 0; i--) {
      const r = this.ripples[i];
      r.step();
      if (r instanceof BigRipple ? r.done() : r.life <= 0) this.ripples.splice(i, 1);
    }
  }
  splash(x: number, y: number) {
    // 点击涟漪：随机 2-3 圈同心，全屏扩散反弹后渐隐
    this.ripples.push(new BigRipple(x, y, this.w, this.h));
  }
  draw() {
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.w, this.h);
    for (const k of this.fish) k.drawBody(ctx, true, 9); // 淡淡一层鱼影
    for (const k of this.fish) k.drawBody(ctx, false);
    for (const r of this.ripples) r.draw(ctx);
  }
}

export default function InkFish({ count = 8 }: { count?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const pond = new Pond(canvas, count);
    let stop = () => {};
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
    let raf = 0, last = performance.now(), acc = 0, dead = false;

    const draw = () => pond.draw();
    if (reduce.matches) { draw(); return () => {}; } // 静帧一画

    const h = 1 / 60;
    const frame = (t: number) => {
      raf = requestAnimationFrame(frame);
      let dt = (t - last) / 1000;
      last = t;
      if (dt > 0.25) dt = 0.25;
      acc += dt;
      let n = 0;
      while (acc >= h && n < 4) { pond.step(); acc -= h; n++; }
      draw();
    };
    const start = () => { last = performance.now(); acc = 0; raf = requestAnimationFrame(frame); };
    const onVis = () => {
      if (document.hidden) cancelAnimationFrame(raf);
      else if (!dead) start();
    };
    document.addEventListener("visibilitychange", onVis);
    start();
    stop = () => { dead = true; cancelAnimationFrame(raf); };

    // 指针避让 + 点击涟漪：画布 pointer-events:none，坐标从 window 换算
    const toLocal = (e: PointerEvent) => {
      const r = canvas.getBoundingClientRect();
      return { x: e.clientX - r.left, y: e.clientY - r.top, r };
    };
    const onMove = (e: PointerEvent) => {
      const { x, y, r } = toLocal(e);
      const inside = x >= -20 && y >= -20 && x <= r.width + 20 && y <= r.height + 20;
      pond.pointer.active = inside;
      pond.pointer.x = x; pond.pointer.y = y;
    };
    const onDown = (e: PointerEvent) => {
      const { x, y, r } = toLocal(e);
      if (x < 0 || y < 0 || x > r.width || y > r.height) return;
      pond.splash(x, y);
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    window.addEventListener("pointerdown", onDown, { passive: true });

    // 宽度变化才重建（DPR/尺寸变化重设画布）
    let lastW = canvas.getBoundingClientRect().width;
    let resizeT = 0;
    const ro = new ResizeObserver(() => {
      clearTimeout(resizeT);
      resizeT = window.setTimeout(() => {
        const w = canvas.getBoundingClientRect().width;
        if (Math.abs(w - lastW) < 1) return;
        lastW = w;
        pond.resize();
      }, 120);
    });
    ro.observe(canvas);

    return () => {
      stop();
      ro.disconnect();
      clearTimeout(resizeT);
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerdown", onDown);
    };
  }, [count]);

  return <canvas ref={ref} className="home-fish" aria-hidden="true" />;
}
