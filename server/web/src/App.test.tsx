import { screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { App } from "./App";
import { renderWithProviders } from "./test/render";

test("renders the app", () => {
  renderWithProviders(<App />);
  expect(screen.getByRole("main")).toBeInTheDocument();
});
