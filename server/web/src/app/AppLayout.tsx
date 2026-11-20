import { AppShell, Burger, Group, NavLink, Text } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { useTranslation } from "react-i18next";
import { Link, Outlet, useLocation } from "react-router";
import { useCan } from "../features/auth/can";
import { NAV_ITEMS } from "./navItems";

export function AppLayout() {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const can = useCan();
  const [opened, { toggle, close }] = useDisclosure(false);
  const items = NAV_ITEMS.filter(
    (item) => item.permission === undefined || can(item.permission),
  );

  return (
    <AppShell
      header={{ height: 56 }}
      navbar={{
        width: 240,
        breakpoint: "sm",
        collapsed: { mobile: !opened },
      }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md">
          <Burger
            opened={opened}
            onClick={toggle}
            hiddenFrom="sm"
            size="sm"
            aria-label={opened ? t("navigation.close") : t("navigation.open")}
            aria-expanded={opened}
          />
          <Text fw={700}>{t("appName")}</Text>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="xs" aria-label={t("navigation.main")}>
        {items.map((item) => (
          <NavLink
            key={item.path}
            component={Link}
            to={item.path}
            label={t(item.label)}
            active={
              pathname === item.path || pathname.startsWith(`${item.path}/`)
            }
            onClick={close}
          />
        ))}
      </AppShell.Navbar>
      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
