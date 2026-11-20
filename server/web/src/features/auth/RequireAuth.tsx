import { Button, Center, Loader, Stack, Text } from "@mantine/core";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Navigate, useLocation } from "react-router";
import { ApiError } from "../../api/ApiError";
import { errorText } from "../../api/errorText";
import { loginPath } from "../../api/navigation";
import { useMe } from "./api";

export const CHANGE_PASSWORD_PATH = "/change-password";

/**
 * Renders `children` only for a logged-in user who doesn't have to change
 * their password first.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const { t: tErrors } = useTranslation("errors");
  const location = useLocation();
  const me = useMe();

  if (me.isPending) {
    return (
      <Center h="100vh">
        <Loader aria-label={t("loading")} />
      </Center>
    );
  }

  if (me.isError) {
    // The server answers 403 rather than 401 for a session it no longer
    // accepts (a disabled user, a bumped token version).
    if (
      me.error instanceof ApiError &&
      (me.error.status === 401 || me.error.status === 403)
    ) {
      return <Navigate to={loginPath(location)} replace />;
    }
    return (
      <Center h="100vh">
        <Stack align="center">
          <Text>{errorText(tErrors, me.error)}</Text>
          <Button onClick={() => void me.refetch()}>{t("retry")}</Button>
        </Stack>
      </Center>
    );
  }

  if (me.data.must_change_password) {
    return <Navigate to={CHANGE_PASSWORD_PATH} replace />;
  }

  return children;
}
