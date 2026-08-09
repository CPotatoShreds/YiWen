// 数值 + 变化动效：数字短暂高亮，旁侧浮出 +N/-N 徽标后淡出。名望/见闻通用。
import { useStatDelta } from "../hooks/useStatDelta";

interface Props {
  value: number;
  className?: string; // 数字本身的样式类（如 score__value accent / rp）
}

export default function StatNumber({ value, className }: Props) {
  const flash = useStatDelta(value);
  const up = flash ? flash.delta > 0 : false;
  return (
    <span className={[className, flash ? "stat-flash" : ""].filter(Boolean).join(" ")}>
      {value}
      {flash && (
        <span key={flash.key} className={`stat-delta ${up ? "is-up" : "is-down"}`}>
          {up ? `+${flash.delta}` : flash.delta}
        </span>
      )}
    </span>
  );
}
