// 后端时间戳均为无时区 UTC（func.now() 落 naive UTC），序列化不带时区标记。
// 直接 new Date(iso) 会当成本地时间，差 8 小时；统一补 Z 按 UTC 解析，再转本地（北京时区）显示。
export function parseUtc(iso: string): Date {
  return new Date(iso + "Z");
}
