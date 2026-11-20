import {
  Alert,
  Button,
  Center,
  Group,
  Paper,
  PasswordInput,
  Stack,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { notifications } from "@mantine/notifications";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useSearchParams } from "react-router";
import { ApiError } from "../../api/ApiError";
import { api } from "../../api/client";
import { applyApiError } from "../../api/formErrors";
import { queryKeys } from "../../api/queryKeys";
import { useLogout, useMe } from "./api";
import { PASSWORD_MAX, PASSWORD_MIN, passwordLengthOk } from "./passwordLength";
import { safeNext } from "./safeNext";

interface PasswordValues {
  current_password: string;
  new_password: string;
  confirm_password: string;
}

/** Rendered inside `RequireAuth allowPasswordChange`, so `me` has loaded. */
export function ChangePasswordPage() {
  const { t } = useTranslation("auth");
  const { t: tErrors } = useTranslation("errors");
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const forced = useMe().data?.must_change_password ?? false;
  const logout = useLogout();

  const form = useForm<PasswordValues>({
    mode: "uncontrolled",
    initialValues: {
      current_password: "",
      new_password: "",
      confirm_password: "",
    },
    validate: {
      current_password: (value) =>
        value ? null : t("changePassword.required"),
      new_password: (value) =>
        passwordLengthOk(value)
          ? null
          : t("changePassword.length", {
              min: PASSWORD_MIN,
              max: PASSWORD_MAX,
            }),
      confirm_password: (value, values) =>
        value === values.new_password ? null : t("changePassword.mismatch"),
    },
  });

  const change = useMutation({
    mutationFn: async ({ current_password, new_password }: PasswordValues) => {
      await api.POST("/api/auth/password", {
        body: { current_password, new_password },
      });
    },
    // Waiting for `me` keeps RequireAuth from seeing the old
    // must_change_password and sending a forced user straight back here.
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.me });
      notifications.show({ color: "green", message: t("changePassword.done") });
      void navigate(next, { replace: true });
    },
    onError: (error) => {
      if (
        error instanceof ApiError &&
        error.status === 403 &&
        error.field === "current_password"
      ) {
        form.setFieldError(
          "current_password",
          t("changePassword.wrongCurrent"),
        );
        return;
      }
      applyApiError(form, error, tErrors);
    },
  });

  return (
    <Center mih="100vh" p="md">
      <Paper w="100%" maw={360} p="lg" withBorder={true}>
        <form
          onSubmit={form.onSubmit((values) => change.mutate(values))}
          noValidate={true}
        >
          <Stack>
            <Title order={1}>{t("changePassword.title")}</Title>
            {forced && <Alert color="blue">{t("changePassword.forced")}</Alert>}
            <PasswordInput
              label={t("changePassword.current")}
              autoComplete="current-password"
              required={true}
              key={form.key("current_password")}
              {...form.getInputProps("current_password")}
            />
            <PasswordInput
              label={t("changePassword.new")}
              autoComplete="new-password"
              required={true}
              key={form.key("new_password")}
              {...form.getInputProps("new_password")}
            />
            <PasswordInput
              label={t("changePassword.confirm")}
              autoComplete="new-password"
              required={true}
              key={form.key("confirm_password")}
              {...form.getInputProps("confirm_password")}
            />
            <Button type="submit" loading={change.isPending}>
              {t("changePassword.submit")}
            </Button>
            <Group justify="center">
              {forced ? (
                <Button
                  variant="subtle"
                  loading={logout.isPending}
                  onClick={() => logout.mutate()}
                >
                  {t("changePassword.logout")}
                </Button>
              ) : (
                <Button variant="subtle" component={Link} to={next}>
                  {t("changePassword.cancel")}
                </Button>
              )}
            </Group>
          </Stack>
        </form>
      </Paper>
    </Center>
  );
}
