import { act, screen, waitFor, within } from "@testing-library/react";
import { expect, test } from "vitest";
import { renderWithProviders } from "../test/render";
import { confirmDanger } from "./confirmDanger";

function open() {
  const view = renderWithProviders(<div />);
  let result!: Promise<boolean>;
  act(() => {
    result = confirmDanger({
      title: "Delete user?",
      message: "This can't be undone.",
      target: "Kid",
      confirmLabel: "Delete",
    });
  });
  return { ...view, result };
}

test("names the target and resolves true on confirm", async () => {
  const { user, result } = open();
  const dialog = within(await screen.findByRole("dialog"));
  expect(dialog.getByText("Delete user?")).toBeInTheDocument();
  expect(dialog.getByText("This can't be undone.")).toBeInTheDocument();
  expect(dialog.getByText("Kid")).toBeInTheDocument();
  await user.click(dialog.getByRole("button", { name: "Delete" }));
  await expect(result).resolves.toBe(true);
});

test("the confirm button is red", async () => {
  open();
  const dialog = within(await screen.findByRole("dialog"));
  const button = dialog.getByRole("button", { name: "Delete" });
  expect(button.getAttribute("style")).toContain("--mantine-color-red");
});

test("cancel resolves false", async () => {
  const { user, result } = open();
  const dialog = within(await screen.findByRole("dialog"));
  await user.click(dialog.getByRole("button", { name: "Cancel" }));
  await expect(result).resolves.toBe(false);
});

test("Escape resolves false", async () => {
  const { user, result } = open();
  await screen.findByRole("dialog");
  await user.keyboard("{Escape}");
  await expect(result).resolves.toBe(false);
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
});
