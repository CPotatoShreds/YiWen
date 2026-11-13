import { useQuery } from "@tanstack/react-query";
import { request } from "./api";

export function useApiQuery<T>(path: string, enabled = true) {
  return useQuery<T>({
    queryKey: ["api", path],
    queryFn: ({ signal }) => request<T>(path, { signal }),
    enabled,
  });
}
