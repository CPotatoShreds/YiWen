/**
 * 与跳转有关的纯函数。单独放一个文件，避免污染组件文件（fast-refresh 要求组件文件只导出组件）。
 */

/**
 * 从 RequireAuth 塞进 location.state 的来处里取出原目标路径。
 * 没有来处返回 null —— 调用方自行决定回落地址。
 */
export function returnTo(state: unknown): string | null {
  const from = (state as { from?: { pathname?: unknown } } | null)?.from;
  return typeof from?.pathname === "string" && from.pathname.startsWith("/") ? from.pathname : null;
}
