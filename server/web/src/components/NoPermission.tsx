import { Stack, Text, Title } from "@mantine/core";
import { useTranslation } from "react-i18next";

export function NoPermission() {
  const { t } = useTranslation();
  return (
    <Stack align="flex-start">
      <Title order={1}>{t("noPermission.title")}</Title>
      <Text>{t("noPermission.message")}</Text>
    </Stack>
  );
}
