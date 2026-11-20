import { useTranslation } from "react-i18next";
import { Navigate, Route, Routes } from "react-router";
import { AppLayout } from "./app/AppLayout";
import { NavigationBridge } from "./app/NavigationBridge";
import { NotFound } from "./components/NotFound";
import { PagePlaceholder } from "./components/PagePlaceholder";

export function App() {
  const { t } = useTranslation();
  return (
    <>
      <NavigationBridge />
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<Navigate to="/devices" replace />} />
          <Route
            path="devices"
            element={<PagePlaceholder title={t("nav.devices")} />}
          />
          <Route
            path="devices/:id"
            element={<PagePlaceholder title={t("pages.device")} />}
          />
          <Route
            path="users"
            element={<PagePlaceholder title={t("nav.users")} />}
          />
          <Route
            path="users/:id"
            element={<PagePlaceholder title={t("pages.user")} />}
          />
          <Route
            path="server-settings"
            element={<PagePlaceholder title={t("nav.serverSettings")} />}
          />
          <Route
            path="account"
            element={<PagePlaceholder title={t("nav.account")} />}
          />
        </Route>
        <Route
          path="login"
          element={<PagePlaceholder title={t("pages.login")} />}
        />
        <Route
          path="change-password"
          element={<PagePlaceholder title={t("pages.changePassword")} />}
        />
        <Route
          path="invite"
          element={<PagePlaceholder title={t("pages.invite")} />}
        />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </>
  );
}
