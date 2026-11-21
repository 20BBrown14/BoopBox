import { Stack, Text } from "@mantine/core";
import { modals } from "@mantine/modals";
import i18n from "../i18n";

interface ConfirmDangerOptions {
  title: string;
  message: string;
  /** What the action destroys, shown on its own line so it can't be missed. */
  target: string;
  confirmLabel: string;
}

/** Resolves true on confirm, false on cancel or any other close. */
export function confirmDanger({
  title,
  message,
  target,
  confirmLabel,
}: ConfirmDangerOptions): Promise<boolean> {
  const t = i18n.getFixedT(null, "common");
  return new Promise((resolve) => {
    modals.openConfirmModal({
      title,
      children: (
        <Stack gap="xs">
          <Text size="sm">{message}</Text>
          <Text fw={700}>{target}</Text>
        </Stack>
      ),
      labels: { confirm: confirmLabel, cancel: t("cancel") },
      confirmProps: { color: "red" },
      onConfirm: () => resolve(true),
      // Also fires after a confirm, when the promise is already settled.
      onClose: () => resolve(false),
    });
  });
}
