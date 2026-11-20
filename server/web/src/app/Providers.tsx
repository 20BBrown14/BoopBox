import { MantineProvider } from "@mantine/core";
import { ModalsProvider } from "@mantine/modals";
import { Notifications } from "@mantine/notifications";
import { type QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { I18nextProvider, useTranslation } from "react-i18next";
import i18n from "../i18n";
import { theme } from "./theme";

function TranslatedModals({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  return (
    <ModalsProvider labels={{ confirm: t("confirm"), cancel: t("cancel") }}>
      {children}
    </ModalsProvider>
  );
}

export function Providers({
  queryClient,
  children,
}: {
  queryClient: QueryClient;
  children: ReactNode;
}) {
  // No <ColorSchemeScript />: tools/colorSchemePlugin.ts serves its script as
  // /color-scheme.js, because the CSP blocks inline scripts.
  return (
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={queryClient}>
        <MantineProvider theme={theme} defaultColorScheme="auto">
          <Notifications />
          <TranslatedModals>{children}</TranslatedModals>
        </MantineProvider>
      </QueryClientProvider>
    </I18nextProvider>
  );
}
