import {
  Alert,
  Button,
  Center,
  Loader,
  Paper,
  PasswordInput,
  Stack,
  TextInput,
  Title,
} from "@mantine/core";
import { useForm } from "@mantine/form";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Navigate, useSearchParams } from "react-router";
import { ApiError } from "../../api/ApiError";
import { api, bodyOf } from "../../api/client";
import { applyApiError } from "../../api/formErrors";
import { queryKeys } from "../../api/queryKeys";
import { useMe } from "./api";
import { safeNext } from "./safeNext";

interface LoginValues {
  username: string;
  password: string;
}

export function LoginPage() {
  const { t } = useTranslation("auth");
  const { t: tErrors } = useTranslation("errors");
  const { t: tCommon } = useTranslation();
  const [params] = useSearchParams();
  const next = safeNext(params.get("next"));
  const queryClient = useQueryClient();
  const me = useMe();

  const required = (value: string) =>
    value.trim() ? null : t("login.required");
  const form = useForm<LoginValues>({
    mode: "uncontrolled",
    initialValues: { username: "", password: "" },
    validate: { username: required, password: required },
  });

  const login = useMutation({
    mutationFn: async (values: LoginValues) =>
      bodyOf(await api.POST("/api/auth/login", { body: values })),
    // Once `me` refetches, the redirect below takes over.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.me }),
    onError: (error) => {
      if (!(error instanceof ApiError && error.status === 401)) {
        applyApiError(form, error, tErrors);
      }
    },
  });

  if (me.isSuccess) return <Navigate to={next} replace={true} />;
  if (me.isPending) {
    return (
      <Center h="100vh">
        <Loader aria-label={tCommon("loading")} />
      </Center>
    );
  }

  const failed = login.error instanceof ApiError && login.error.status === 401;

  return (
    <Center mih="100vh" p="md">
      <Paper w="100%" maw={360} p="lg" withBorder={true}>
        <form
          onSubmit={form.onSubmit((values) => login.mutate(values))}
          noValidate={true}
        >
          <Stack>
            <Title order={1}>{t("login.title")}</Title>
            {failed && (
              <Alert color="red" role="alert">
                {t("login.failed")}
              </Alert>
            )}
            <TextInput
              label={t("login.username")}
              autoComplete="username"
              autoCapitalize="none"
              required={true}
              key={form.key("username")}
              {...form.getInputProps("username")}
            />
            <PasswordInput
              label={t("login.password")}
              autoComplete="current-password"
              required={true}
              key={form.key("password")}
              {...form.getInputProps("password")}
            />
            <Button type="submit" loading={login.isPending}>
              {t("login.submit")}
            </Button>
          </Stack>
        </form>
      </Paper>
    </Center>
  );
}
