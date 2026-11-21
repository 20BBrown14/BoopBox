import { screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { renderWithProviders } from "../test/render";
import { Timestamp } from "./Timestamp";

const NOW = new Date("2026-11-13T09:30:00.000Z");

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: NOW });
});

afterEach(() => {
  vi.useRealTimers();
});

test("shows relative text in a <time> element", () => {
  renderWithProviders(<Timestamp value="2026-11-13T09:25:00.000Z" />);
  const time = screen.getByText("5 minutes ago");
  expect(time.tagName).toBe("TIME");
  expect(time).toHaveAttribute("datetime", "2026-11-13T09:25:00.000Z");
});

test("the tooltip shows the local and UTC times", async () => {
  const { user } = renderWithProviders(
    <Timestamp value="2026-11-13T09:25:00.000Z" />,
  );
  await user.hover(screen.getByText("5 minutes ago"));
  const tooltip = await screen.findByRole("tooltip");
  expect(tooltip).toHaveTextContent(
    /^Local: .+UTC: Nov 13, 2026, 9:25:00\sAM$/,
  );
});

test("the tooltip also opens from the keyboard", async () => {
  const { user } = renderWithProviders(
    <Timestamp value="2026-11-13T09:25:00.000Z" />,
  );
  await user.tab();
  expect(await screen.findByRole("tooltip")).toHaveTextContent("UTC:");
});

test("null is never", () => {
  renderWithProviders(<Timestamp value={null} />);
  expect(screen.getByText("Never")).toBeInTheDocument();
});
