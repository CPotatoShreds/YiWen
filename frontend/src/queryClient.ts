import { QueryClient } from "@tanstack/react-query";

// Cookie 会话数据仅驻留内存；退出时清空，禁止持久化到 localStorage。
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 10_000, gcTime: 300_000, retry: false, refetchOnWindowFocus: true },
    mutations: { retry: false },
  },
});
