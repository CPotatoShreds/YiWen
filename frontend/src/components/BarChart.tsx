interface BarDatum { label: string; value: number }

export default function BarChart({ data }: { data: BarDatum[] }) {
  const width = 640;
  const height = 190;
  const left = 28;
  const right = 10;
  const top = 22;
  const bottom = 30;
  const chartHeight = height - top - bottom;
  const chartWidth = width - left - right;
  const max = Math.max(...data.map((d) => d.value), 1);
  const slot = data.length ? chartWidth / data.length : chartWidth;
  const barWidth = Math.min(44, slot * 0.58);
  const hasValues = data.some((d) => d.value > 0);

  return (
    <div className="bar-chart" role="img" aria-label="近七日请求量">
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
        {[0, 0.33, 0.66, 1].map((ratio) => {
          const y = top + chartHeight * (1 - ratio);
          return <line key={ratio} x1={left} x2={width - right} y1={y} y2={y} className="bar-chart__grid" />;
        })}
        <line x1={left} x2={width - right} y1={top + chartHeight} y2={top + chartHeight} className="bar-chart__axis" />
        {data.map((d, i) => {
          const barHeight = hasValues ? (d.value / max) * chartHeight : 0;
          const x = left + slot * i + (slot - barWidth) / 2;
          const y = top + chartHeight - barHeight;
          return (
            <g key={d.label}>
              {barHeight > 0 && <rect x={x} y={y} width={barWidth} height={barHeight} rx="3" className="bar-chart__bar" />}
              <text x={x + barWidth / 2} y={Math.max(top - 5, y - 6)} textAnchor="middle" className="bar-chart__value">{d.value}</text>
              <text x={x + barWidth / 2} y={height - 9} textAnchor="middle" className="bar-chart__label">{d.label}</text>
            </g>
          );
        })}
      </svg>
      {!hasValues && <p className="bar-chart__empty">近 7 日无请求</p>}
    </div>
  );
}
