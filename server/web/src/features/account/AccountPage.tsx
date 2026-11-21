import {
  Button,
  Group,
  NativeSelect,
  Paper,
  SegmentedControl,
  Stack,
  Text,
  Title,
  useMantineColorScheme,
  type MantineColorScheme,
} from "@mantine/core";
import { modals } from "@mantine/modals";
import { notifications } from "@mantine/notifications";
import { type ReactNode, useId } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";
import { LANGUAGES } from "../../i18n/languages";
import { type Me, useLogout, useLogoutAll, useMe } from "../auth/api";
import { CHANGE_PASSWORD_PATH } from "../auth/RequireAuth";

const COLOR_SCHEMES = ["light", "dark", "auto"] as const;

function isColorScheme(value: string): value is MantineColorScheme {
  return (COLOR_SCHEMES as readonly string[]).includes(value);
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  const headingId = useId();
  return (
    <Paper
      p="md"
      withBorder={true}
      component="section"
      aria-labelledby={headingId}
    >
      <Stack>
        <Title order={2} size="h4" id={headingId}>
          {title}
        </Title>
        {children}
      </Stack>
    </Paper>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <Text size="sm" c="dimmed">
        {label}
      </Text>
      <Text>{value}</Text>
    </div>
  );
}

function LoginSection({ me }: { me: Me }) {
  const { t } = useTranslation("account");
  const login = me.login;
  return (
    <Section title={t("login.title")}>
      <Field label={t("login.displayName")} value={me.display_name} />
      {login === null ? (
        <Text c="dimmed">{t("login.none")}</Text>
      ) : login.provider === "local" ? (
        <Field label={t("login.username")} value={login.username ?? ""} />
      ) : (
        <Field
          label={t("login.method")}
          value={login.label ?? login.provider}
        />
      )}
      {login?.provider === "local" && (
        <Group>
          <Button
            variant="default"
            component={Link}
            to={`${CHANGE_PASSWORD_PATH}?next=${encodeURIComponent("/account")}`}
          >
            {t("login.changePassword")}
          </Button>
        </Group>
      )}
    </Section>
  );
}

function SessionsSection() {
  const { t } = useTranslation("account");
  const { t: tCommon } = useTranslation();
  const logout = useLogout();
  const logoutAll = useLogoutAll();

  const confirmLogoutAll = () =>
    modals.openConfirmModal({
      title: t("sessions.confirmTitle"),
      children: <Text size="sm">{t("sessions.confirmMessage")}</Text>,
      labels: { confirm: t("sessions.logoutAll"), cancel: tCommon("cancel") },
      confirmProps: { color: "red" },
      onConfirm: () =>
        logoutAll.mutate(undefined, {
          onSuccess: () =>
            notifications.show({
              color: "green",
              message: t("sessions.loggedOutAll"),
            }),
        }),
    });

  return (
    <Section title={t("sessions.title")}>
      <Text size="sm" c="dimmed">
        {t("sessions.logoutAllHint")}
      </Text>
      <Group>
        <Button
          variant="default"
          loading={logout.isPending}
          onClick={() => logout.mutate()}
        >
          {t("sessions.logout")}
        </Button>
        <Button
          color="red"
          variant="light"
          loading={logoutAll.isPending}
          onClick={confirmLogoutAll}
        >
          {t("sessions.logoutAll")}
        </Button>
      </Group>
    </Section>
  );
}

function PreferencesSection() {
  const { t, i18n } = useTranslation("account");
  const { colorScheme, setColorScheme } = useMantineColorScheme();
  const colorSchemeLabelId = useId();
  return (
    <Section title={t("preferences.title")}>
      <NativeSelect
        label={t("preferences.language")}
        data={LANGUAGES.map(({ code, name }) => ({ value: code, label: name }))}
        value={i18n.resolvedLanguage}
        onChange={(event) =>
          void i18n.changeLanguage(event.currentTarget.value)
        }
      />
      <Stack gap={4}>
        <Text size="sm" fw={500} id={colorSchemeLabelId}>
          {t("preferences.colorScheme")}
        </Text>
        <SegmentedControl
          aria-labelledby={colorSchemeLabelId}
          value={colorScheme}
          onChange={(value) => {
            if (isColorScheme(value)) setColorScheme(value);
          }}
          data={COLOR_SCHEMES.map((scheme) => ({
            value: scheme,
            label: t(`preferences.${scheme}`),
          }))}
        />
      </Stack>
    </Section>
  );
}

/** Rendered inside `RequireAuth`, so `me` has loaded. */
export function AccountPage() {
  const { t } = useTranslation("account");
  const me = useMe().data;
  return (
    <Stack maw={640}>
      <Title order={1}>{t("title")}</Title>
      {me && <LoginSection me={me} />}
      <SessionsSection />
      <PreferencesSection />
    </Stack>
  );
}
