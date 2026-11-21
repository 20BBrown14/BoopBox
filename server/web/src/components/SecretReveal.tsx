import {
  Button,
  Checkbox,
  CopyButton,
  Group,
  Modal,
  Stack,
  TextInput,
} from "@mantine/core";
import { type ReactNode, useState } from "react";
import { useTranslation } from "react-i18next";

export interface RevealedValue {
  label: string;
  value: string;
}

interface SecretRevealProps {
  opened: boolean;
  title: string;
  secrets: readonly RevealedValue[];
  link?: RevealedValue;
  warning?: ReactNode;
  /** The caller drops the values here, and resets the mutation that held them. */
  onDone: () => void;
}

function CopyField({ label, value }: RevealedValue) {
  const { t } = useTranslation();
  return (
    <TextInput
      label={label}
      value={value}
      readOnly={true}
      onFocus={(event) => event.currentTarget.select()}
      styles={{ input: { fontFamily: "monospace" } }}
      rightSectionWidth={88}
      rightSection={
        <CopyButton value={value}>
          {({ copied, copy }) => (
            <Button
              size="compact-sm"
              variant="subtle"
              color={copied ? "teal" : undefined}
              onClick={copy}
              aria-label={`${copied ? t("secretReveal.copied") : t("secretReveal.copy")}: ${label}`}
            >
              {copied ? t("secretReveal.copied") : t("secretReveal.copy")}
            </Button>
          )}
        </CopyButton>
      }
    />
  );
}

function RevealBody({
  secrets,
  link,
  warning,
  onDone,
}: Omit<SecretRevealProps, "opened" | "title">) {
  const { t } = useTranslation();
  const [saved, setSaved] = useState(false);
  return (
    <Stack>
      {warning}
      {secrets.map((secret) => (
        <CopyField key={secret.label} {...secret} />
      ))}
      {link && <CopyField {...link} />}
      <Checkbox
        label={t("secretReveal.saved")}
        checked={saved}
        onChange={(event) => setSaved(event.currentTarget.checked)}
      />
      <Group justify="flex-end">
        <Button disabled={!saved} onClick={onDone}>
          {t("secretReveal.done")}
        </Button>
      </Group>
    </Stack>
  );
}

/**
 * Shows values the server returns only once. The only way out is "Done",
 * after confirming they were saved.
 */
export function SecretReveal({ opened, title, ...body }: SecretRevealProps) {
  return (
    <Modal
      opened={opened}
      onClose={() => {}}
      title={title}
      closeOnClickOutside={false}
      closeOnEscape={false}
      withCloseButton={false}
      centered={true}
    >
      {/* Mounted only while open, so the checkbox starts unticked every time. */}
      {opened && <RevealBody {...body} />}
    </Modal>
  );
}
