// 时间展示：后端 created_at 是 naive UTC（数据库列无时区，写入时已抹掉 tzinfo），
// 直接 new Date() 会被当成本地时间解析、差出一个时区，所以无时区后缀时补 Z 再解析。

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

function toLocal(iso?: string | null): Date | null {
  if (!iso) return null;
  const hasZone = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(iso);
  const date = new Date(hasZone ? iso : `${iso}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** 记录预览用短格式："2026-11-12T00:56:00" → "11/12 8:56"（本地时区，小时不补零） */
export function formatShortDateTime(iso?: string | null): string {
  const date = toLocal(iso);
  if (!date) return "";
  return `${pad(date.getMonth() + 1)}/${pad(date.getDate())} ${date.getHours()}:${pad(date.getMinutes())}`;
}
