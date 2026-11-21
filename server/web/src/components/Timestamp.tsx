import { Stack, Text, Tooltip } from "@mantine/core";
import { useTranslation } from "react-i18next";
import { formatDateTime, formatRelative } from "../lib/format";

/** A stored UTC time as relative text, with the full local and UTC times on hover, focus or touch. */
export function Timestamp({ value }: { value: string | null }) {
  const { t, i18n } = useTranslation();
  if (value === null) return <span>{t("timestamp.never")}</span>;
  const lang = i18n.resolvedLanguage ?? i18n.language;
  return (
    <Tooltip
      label={
        <Stack gap={0}>
          <Text size="sm">
            {t("timestamp.local", { time: formatDateTime(value, lang) })}
          </Text>
          <Text size="sm">
            {t("timestamp.utc", { time: formatDateTime(value, lang, "UTC") })}
          </Text>
        </Stack>
      }
      events={{ hover: true, focus: true, touch: true }}
    >
      <time dateTime={value} tabIndex={0}>
        {formatRelative(value, new Date(), lang)}
      </time>
    </Tooltip>
  );
}
