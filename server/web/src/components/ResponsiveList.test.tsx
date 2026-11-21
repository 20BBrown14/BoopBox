import { screen, within } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import { renderWithProviders } from "../test/render";
import { type Column, ResponsiveList } from "./ResponsiveList";

interface Person {
  id: number;
  name: string;
  role: string;
}

const PEOPLE: Person[] = [
  { id: 1, name: "Owner", role: "Admin" },
  { id: 2, name: "Kid", role: "Listener" },
];

const COLUMNS: Column<Person>[] = [
  { id: "role", header: "Role", render: (p) => p.role },
  { id: "name", header: "Name", render: (p) => p.name, primary: true },
];

function screenSize(wide: boolean) {
  vi.spyOn(window, "matchMedia").mockImplementation(
    (query) =>
      ({
        matches: wide && query.includes("min-width"),
        media: query,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
      }) as unknown as MediaQueryList,
  );
}

function renderList(
  props: Partial<Parameters<typeof ResponsiveList<Person>>[0]> = {},
) {
  return renderWithProviders(
    <ResponsiveList
      rows={PEOPLE}
      rowKey={(p) => p.id}
      columns={COLUMNS}
      empty={<p>Nobody here</p>}
      {...props}
    />,
  );
}

describe("on a wide screen", () => {
  test("renders a table with every column", () => {
    screenSize(true);
    renderList();
    const table = screen.getByRole("table");
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((th) => th.textContent),
    ).toEqual(["Role", "Name"]);
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((row) => row.textContent)).toEqual([
      "AdminOwner",
      "ListenerKid",
    ]);
  });

  test("rowHref puts one link per row, on the primary cell", () => {
    screenSize(true);
    renderList({ rowHref: (p) => `/people/${p.id}` });
    const links = screen.getAllByRole("link");
    expect(
      links.map((link) => [link.textContent, link.getAttribute("href")]),
    ).toEqual([
      ["Owner", "/people/1"],
      ["Kid", "/people/2"],
    ]);
  });

  test("without rowHref nothing is a link", () => {
    screenSize(true);
    renderList();
    expect(screen.queryAllByRole("link")).toEqual([]);
  });
});

describe("on a phone", () => {
  test("renders cards titled by the primary column", () => {
    screenSize(false);
    renderList();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    const owner = screen.getByText("Owner");
    const card = owner.closest(".mantine-Card-root") as HTMLElement;
    expect(within(card).getByText("Role")).toBeInTheDocument();
    expect(within(card).getByText("Admin")).toBeInTheDocument();
    expect(within(card).queryByText("Name")).not.toBeInTheDocument();
  });

  test("rowHref makes each card a link", () => {
    screenSize(false);
    renderList({ rowHref: (p) => `/people/${p.id}` });
    const links = screen.getAllByRole("link");
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "/people/1",
      "/people/2",
    ]);
    expect(links[0]).toHaveTextContent("Owner");
    expect(links[0]).toHaveTextContent("Admin");
  });
});

test.each([true, false])("no rows shows the empty state (wide: %s)", (wide) => {
  screenSize(wide);
  renderList({ rows: [] });
  expect(screen.getByText("Nobody here")).toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});

test("the first column is primary when none is marked", () => {
  screenSize(true);
  renderList({
    columns: COLUMNS.map((column) => ({ ...column, primary: false })),
    rowHref: (p) => `/people/${p.id}`,
  });
  expect(screen.getAllByRole("link").map((link) => link.textContent)).toEqual([
    "Admin",
    "Listener",
  ]);
});
