import { useEffect, useRef, useState } from "react";

/** 数值变化检测：数值变化时返回最近一次差值（供浮动 ±N 徽标 + 高亮动画）。首次挂载不触发。 */
export function useStatDelta(value: number) {
  const prevRef = useRef<number | null>(null);
  const keyRef = useRef(0); // 递增 key：同一差值重复出现也强制重放动画
  const [flash, setFlash] = useState<{ delta: number; key: number } | null>(null);

  useEffect(() => {
    const prev = prevRef.current;
    prevRef.current = value;
    if (prev === null || prev === value) return;
    keyRef.current += 1;
    setFlash({ delta: value - prev, key: keyRef.current });
  }, [value]);

  return flash;
}
