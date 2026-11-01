import { useEffect, useRef } from "react";
import { InkScene, TAIL_UNITS, UNIT_LINE_GAP, drawSegment } from "../inkScene";

/**
 * 一行的实际耗时（秒）。原页「1.0×」是把整段笔画时钟压进一个固定 22 秒的进度条
 * （t = 进度 × total），四行正好 22 秒；我们没有进度条也没有终点，只能把这个手感
 * 换算成「每行多少秒」。改这一个数就换节奏。
 */
const ROW_SECONDS = 5.5;
/** 提前生成多少毫秒（真实时间）的行，保证笔尖永远追得上已生成内容。 */
const LOOKAHEAD = 1200;
/** 首屏先铺几行（截图的「04 行」）。之后按需往下长，不设上限。 */
const SEED_ROWS = 4;
/** 画布后备高度一次给够几行；不够就翻倍。改后备高度会清空画面，所以只在必要时做。 */
const ALLOC_ROWS = 12;
/** 距底小于这么多像素才算「停在底部」——只有这时才粘底跟随，用户上滑即脱离。 */
const STICK_SLOP = 12;
/** 墨色透明度：比正文淡一档，读得出「还在写」。 */
const INK_ALPHA = 0.62;

/**
 * 推演占位：一段自己往下写的墨迹（算法见 ../inkScene.ts）。
 *
 * 没有终点，也没有「写完了」的状态——行是无限加的，写超一屏由书页自己的滚动条接管。
 * 视口粘底跟随：停在底部时跟着滚，用户一上滑就停在他滑到的地方。
 * 纯画布 + 一个 rAF，卸载即停，不留定时器。
 */
export function InkWriting() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const host = canvas?.parentElement;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !host || !ctx) return;

    const scroller = host.closest<HTMLElement>(".scenario-manuscript__body");
    const inkRgb = getComputedStyle(host).getPropertyValue("--ink-rgb").trim() || "47, 43, 38";
    const ink = `rgba(${inkRgb}, ${INK_ALPHA})`;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // 行高就是格线的行高：墨迹按它缩放，于是每一行必然落在一条格线带里。
    // 断点切换时 --lh 会从 38px 变 33px，所以每次重建都要重读。
    let scale = 1;

    let scene = new InkScene(1, 1);
    let cssWidth = 0;
    let allocated = ALLOC_ROWS;
    let moment = 0;
    /** 真实毫秒 → 笔画时钟毫秒的倍率：一行按 ROW_SECONDS 秒走完。 */
    let pace = 1;
    let cursor = 0;
    let point = 0;
    let raf = 0;
    let lastTime = 0;
    let stick = true;
    let disposed = false;
    let resizeTimer = 0;

    /** 画布只报「已写行」的高度，多出来的后备高度由容器裁掉，滚动条才按真实内容长度出现。 */
    const syncHeight = () => {
      host.style.height = `${scene.heightUnits * scale}px`;
      if (stick && scroller) scroller.scrollTop = scroller.scrollHeight;
    };

    const advanceTo = (target: number) => {
      for (; cursor < scene.strokes.length; ) {
        const stroke = scene.strokes[cursor];
        if (target < stroke.start) break;
        const fraction = Math.max(0, Math.min(1, (target - stroke.start) / stroke.duration));
        const distance = fraction * stroke.length;
        while (point + 1 < stroke.pts.length && stroke.pts[point + 1].d <= distance) {
          point += 1;
          drawSegment(ctx, stroke, point, ink);
        }
        if (fraction < 1) break;
        cursor += 1;
        point = 0;
      }
    };

    const clear = () => {
      ctx.save();
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.restore();
    };

    const redraw = (target: number) => {
      clear();
      cursor = 0;
      point = 0;
      advanceTo(target);
    };

    const sizeCanvas = () => {
      const totalUnits = allocated * UNIT_LINE_GAP + TAIL_UNITS;
      canvas.width = Math.round(cssWidth * ratio);
      canvas.height = Math.round(totalUnits * scale * ratio);
      canvas.style.height = `${totalUnits * scale}px`;
      ctx.setTransform(scale * ratio, 0, 0, scale * ratio, 0, 0);
    };

    /** 后备高度翻倍：离屏拷贝比「重画所有笔画」便宜得多，后者在几十行时是几百毫秒。 */
    const grow = () => {
      const copy = document.createElement("canvas");
      copy.width = canvas.width;
      copy.height = canvas.height;
      copy.getContext("2d")?.drawImage(canvas, 0, 0);
      allocated *= 2;
      sizeCanvas();
      if (copy.width > 0) ctx.drawImage(copy, 0, 0, copy.width / (scale * ratio), copy.height / (scale * ratio));
    };

    const ensureRows = (until: number): boolean => {
      let staged = false;
      while (scene.total <= until) {
        if (scene.rows + 1 > allocated) grow();
        scene.appendRow();
        staged = true;
      }
      return staged;
    };

    const build = () => {
      cssWidth = Math.max(160, host.clientWidth);
      const measured = Number.parseFloat(
        getComputedStyle(scroller ?? host).getPropertyValue("--lh"),
      );
      scale = (measured || 38) / UNIT_LINE_GAP;
      scene = new InkScene(cssWidth / scale, 1);
      allocated = ALLOC_ROWS;
      for (let i = 0; i < SEED_ROWS; i += 1) scene.appendRow();
      // 用前四行的平均时钟定倍率，之后每行长出来的节奏基本一致
      pace = scene.total / scene.rows / (ROW_SECONDS * 1000);
      sizeCanvas();
      syncHeight();
      redraw(moment);
    };

    const tick = (now: number) => {
      raf = 0;
      if (disposed) return;
      const delta = lastTime ? Math.min(now - lastTime, 100) : 0;
      lastTime = now;
      if (!document.hidden) {
        moment += delta * pace;
        if (ensureRows(moment + LOOKAHEAD * pace)) syncHeight();
        advanceTo(moment);
      }
      raf = requestAnimationFrame(tick);
    };

    const onScroll = () => {
      if (!scroller) return;
      stick = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < STICK_SLOP;
    };

    const onVisibility = () => {
      lastTime = 0;
      if (!document.hidden && !raf && !disposed) raf = requestAnimationFrame(tick);
    };

    // 只认宽度变化：我们自己在改容器高度，高度一变也会触发，那不该重建场景
    const observer = new ResizeObserver(() => {
      if (Math.abs(host.clientWidth - cssWidth) < 1) return;
      window.clearTimeout(resizeTimer);
      resizeTimer = window.setTimeout(() => {
        if (disposed || Math.abs(host.clientWidth - cssWidth) < 1) return;
        build();
      }, 120);
    });

    build();
    if (scroller) {
      scroller.scrollTop = 0;
      scroller.addEventListener("scroll", onScroll, { passive: true });
    }
    document.addEventListener("visibilitychange", onVisibility);
    observer.observe(host);

    if (reduced) {
      // 减弱动效：只落一帧半成的墨迹就停，不起 rAF
      moment = scene.total * 0.65;
      advanceTo(moment);
    } else {
      raf = requestAnimationFrame(tick);
    }

    return () => {
      disposed = true;
      if (raf) cancelAnimationFrame(raf);
      window.clearTimeout(resizeTimer);
      observer.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
      // 不复位滚动位置：成卷时占位卸载，读者正读到哪里就该留在哪里
      if (scroller) scroller.removeEventListener("scroll", onScroll);
    };
  }, []);

  return (
    <div className="scenario-veil" aria-hidden="true">
      <canvas ref={canvasRef} />
    </div>
  );
}
