import { screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { renderWithProviders } from "../test/render";
import { NoPermission } from "./NoPermission";

test("explains that the page isn't available", () => {
  renderWithProviders(<NoPermission />);
  expect(
    screen.getByRole("heading", { level: 1, name: "No permission" }),
  ).toBeInTheDocument();
  expect(
    screen.getByText("You don't have permission to view this page."),
  ).toBeInTheDocument();
});
