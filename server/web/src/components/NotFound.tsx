import { Button, Stack, Text, Title } from "@mantine/core";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

export function NotFound() {
  const { t } = useTranslation();
  return (
    <Stack align="flex-start" p="md">
      <Title order={1}>{t("notFound.title")}</Title>
      <Text>{t("notFound.message")}</Text>
      <Button component={Link} to="/devices">
        {t("notFound.home")}
      </Button>
    </Stack>
  );
}
