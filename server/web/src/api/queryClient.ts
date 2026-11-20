import { notifications } from "@mantine/notifications";
import {
  MutationCache,
  QueryCache,
  QueryClient,
  type QueryKey,
} from "@tanstack/react-query";
import i18n from "../i18n";
import { ApiError, NETWORK_CODE } from "./ApiError";
import { getNavigation, LOGIN_PATH, loginPath } from "./navigation";
import { queryKeys } from "./queryKeys";

const MAX_RETRIES = 2;

function retry(failureCount: number, error: Error): boolean {
  if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
    return false;
  }
  return failureCount < MAX_RETRIES;
}

function signOut(client: QueryClient) {
  const navigation = getNavigation();
  const here = navigation?.location ?? globalThis.location;
  // A failed login is a 401 too, and the form deals with it.
  if (here.pathname === LOGIN_PATH) return;

  client.clear();
  const to = loginPath(here);
  if (navigation) navigation.navigate(to, { replace: true });
  else globalThis.location.replace(to);
}

function handleError(client: QueryClient, error: unknown, queryKey?: QueryKey) {
  if (!(error instanceof ApiError)) return;
  const t = i18n.getFixedT(null, "errors");

  if (error.status === 401) {
    signOut(client);
  } else if (error.status === 403) {
    // A 403 that names a field is a rejected input (a wrong current password),
    // and a rejected `me` would only refetch itself.
    if (error.field !== undefined || queryKey?.[0] === queryKeys.me[0]) return;
    notifications.show({
      id: "forbidden",
      color: "red",
      title: t("notify.forbidden.title"),
      message: t("notify.forbidden.message"),
    });
    void client.invalidateQueries({ queryKey: queryKeys.me });
  } else if (error.status >= 500 || error.code === NETWORK_CODE) {
    notifications.show({
      id: "retry",
      color: "red",
      title: t("notify.retry.title"),
      message: t("notify.retry.message"),
    });
  }
}

export function createQueryClient(): QueryClient {
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({
      onError: (error, query) => handleError(client, error, query.queryKey),
    }),
    mutationCache: new MutationCache({
      onError: (error) => handleError(client, error),
    }),
    defaultOptions: { queries: { retry } },
  });
  return client;
}
