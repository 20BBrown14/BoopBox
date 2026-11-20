import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { api, bodyOf } from "../../api/client";
import { LOGIN_PATH } from "../../api/navigation";
import { queryKeys } from "../../api/queryKeys";
import type { components } from "../../api/schema";

export type Me = components["schemas"]["MeOut"];

export function useMe() {
  return useQuery({
    queryKey: queryKeys.me,
    queryFn: async () => bodyOf(await api.GET("/api/me")),
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  return useMutation({
    mutationFn: async () => {
      await api.POST("/api/auth/logout");
    },
    onSuccess: () => {
      queryClient.clear();
      void navigate(LOGIN_PATH, { replace: true });
    },
  });
}
