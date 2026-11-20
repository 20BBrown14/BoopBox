import { useTranslation } from "react-i18next";
import { Navigate, Route, Routes } from "react-router";
import { AppLayout } from "./app/AppLayout";
import { NavigationBridge } from "./app/NavigationBridge";
import { NotFound } from "./components/NotFound";
import { PagePlaceholder } from "./components/PagePlaceholder";
import { ChangePasswordPage } from "./features/auth/ChangePasswordPage";
import { LoginPage } from "./features/auth/LoginPage";
import { RequireAuth } from "./features/auth/RequireAuth";
import { RequirePermission } from "./features/auth/RequirePermission";

export function App() {
  const { t } = useTranslation();
  return (
    <>
      <NavigationBridge />
      <Routes>
        <Route
          element={
            <RequireAuth>
              <AppLayout />
            </RequireAuth>
          }
        >
          <Route
            index={true}
            element={<Navigate to="/devices" replace={true} />}
          />
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
            element={
              <RequirePermission permission="users.manage">
                <PagePlaceholder title={t("nav.users")} />
              </RequirePermission>
            }
          />
          <Route
            path="users/:id"
            element={
              <RequirePermission permission="users.manage">
                <PagePlaceholder title={t("pages.user")} />
              </RequirePermission>
            }
          />
          <Route
            path="server-settings"
            element={
              <RequirePermission permission="server_settings.manage">
                <PagePlaceholder title={t("nav.serverSettings")} />
              </RequirePermission>
            }
          />
          <Route
            path="account"
            element={<PagePlaceholder title={t("nav.account")} />}
          />
        </Route>
        <Route path="login" element={<LoginPage />} />
        <Route
          path="change-password"
          element={
            <RequireAuth allowPasswordChange={true}>
              <ChangePasswordPage />
            </RequireAuth>
          }
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
