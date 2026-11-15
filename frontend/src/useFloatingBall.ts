import { useEffect, useRef, useState, type CSSProperties, type PointerEvent, type KeyboardEvent, type MouseEvent } from "react";

const SIZE = 56;
const MARGIN = 16;
const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(high, value));
function viewport() {
  const view = window.visualViewport;
  return { left: view?.offsetLeft ?? 0, top: view?.offsetTop ?? 0, width: view?.width ?? innerWidth, height: view?.height ?? innerHeight };
}

/** 指针拖动、贴边和键盘替代操作；位置保留在当前刻印的共享页面层。 */
export function useFloatingBall() {
  const [view, setView] = useState(viewport);
  const [dock, setDock] = useState<{ edge: "left" | "right"; ratio: number }>({ edge: "right", ratio: 1 });
  const [free, setFree] = useState<{ x: number; y: number } | null>(null);
  const gesture = useRef<{ id: number; startX: number; startY: number; x: number; y: number; originX: number; originY: number; moved: boolean } | null>(null);
  const suppressClick = useRef(false);
  useEffect(() => {
    const update = () => setView(viewport());
    window.addEventListener("resize", update);
    window.visualViewport?.addEventListener("resize", update);
    window.visualViewport?.addEventListener("scroll", update);
    return () => {
      window.removeEventListener("resize", update);
      window.visualViewport?.removeEventListener("resize", update);
      window.visualViewport?.removeEventListener("scroll", update);
    };
  }, []);
  const left = view.left + MARGIN;
  const right = view.left + view.width - MARGIN - SIZE;
  const top = view.top + MARGIN;
  const bottom = view.top + view.height - MARGIN - SIZE;
  const ball = free ? { x: clamp(free.x, left, right), y: clamp(free.y, top, bottom) }
    : { x: dock.edge === "left" ? left : right, y: top + Math.max(0, bottom - top) * dock.ratio };

  function finish(event: PointerEvent<HTMLButtonElement>) {
    const current = gesture.current;
    if (!current || current.id !== event.pointerId) return;
    gesture.current = null;
    if (current.moved) {
      suppressClick.current = true;
      setDock({ edge: current.x + SIZE / 2 < view.left + view.width / 2 ? "left" : "right", ratio: clamp((current.y - top) / Math.max(1, bottom - top), 0, 1) });
    } else if (event.type === "pointerup" && event.pointerType === "touch") {
      // 浏览器在触摸拖动后可能丢弃下一次兼容 click；轻触由 pointerup 激活一次。
      suppressClick.current = true;
      event.currentTarget.click();
    }
    setFree(null);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  }
  const handlers = {
    onPointerDown(event: PointerEvent<HTMLButtonElement>) {
      if (event.button !== 0 || !event.isPrimary) return;
      suppressClick.current = false;
      gesture.current = { id: event.pointerId, startX: event.clientX, startY: event.clientY, x: ball.x, y: ball.y, originX: ball.x, originY: ball.y, moved: false };
      event.currentTarget.setPointerCapture(event.pointerId);
    },
    onPointerMove(event: PointerEvent<HTMLButtonElement>) {
      const current = gesture.current;
      if (!current || current.id !== event.pointerId) return;
      const dx = event.clientX - current.startX;
      const dy = event.clientY - current.startY;
      if (!current.moved && Math.hypot(dx, dy) < 6) return;
      current.moved = true;
      current.x = clamp(current.originX + dx, left, right);
      current.y = clamp(current.originY + dy, top, bottom);
      setFree({ x: current.x, y: current.y });
    },
    onPointerUp: finish,
    onPointerCancel: finish,
    onLostPointerCapture: finish,
    onClick(event: MouseEvent<HTMLButtonElement>) {
      if (suppressClick.current && event.detail !== 0) {
        event.preventDefault();
        suppressClick.current = false;
      }
    },
    onKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
      if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
      event.preventDefault();
      const key = event.key;
      setDock(current => ({ edge: key === "ArrowLeft" ? "left" : key === "ArrowRight" ? "right" : current.edge,
        ratio: clamp(current.ratio + (key === "ArrowUp" ? -40 : key === "ArrowDown" ? 40 : 0) / Math.max(1, bottom - top), 0, 1) }));
    },
  };

  const width = Math.min(400, view.width - MARGIN * 2);
  let height = Math.min(560, view.height - MARGIN * 2);
  const compact = view.width < width + SIZE + 12 + MARGIN * 2;
  let x = clamp(dock.edge === "right" ? ball.x - 12 - width : ball.x + SIZE + 12, left, view.left + view.width - MARGIN - width);
  let y = clamp(ball.y + SIZE / 2 - height / 2, top, view.top + view.height - MARGIN - height);
  let covered = false;
  if (compact) {
    x = left;
    const above = ball.y - 12 - top;
    const below = view.top + view.height - MARGIN - ball.y - SIZE - 12;
    if (Math.max(above, below) >= 260) {
      height = Math.min(height, Math.max(above, below));
      y = above >= below ? ball.y - 12 - height : ball.y + SIZE + 12;
    } else { y = top; covered = true; }
  }
  return { handlers, dragging: Boolean(free), covered,
    style: {
      "--guess-ball-left": `${ball.x}px`, "--guess-ball-top": `${ball.y}px`,
      "--guess-panel-left": `${x}px`, "--guess-panel-top": `${y}px`,
      "--guess-panel-width": `${width}px`, "--guess-panel-height": `${height}px`,
      "--guess-viewport-height": `${view.height}px`,
    } as CSSProperties,
  };
}
