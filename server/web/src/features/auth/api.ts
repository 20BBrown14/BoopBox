import { useQuery } from "@tanstack/react-query";
import { api, bodyOf } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import type { components } from "../../api/schema";

export type Me = components["schemas"]["MeOut"];

export function useMe() {
  return useQuery({
    queryKey: queryKeys.me,
    queryFn: async () => bodyOf(await api.GET("/api/me")),
  });
}
