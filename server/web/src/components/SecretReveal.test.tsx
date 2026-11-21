import { Button } from "@mantine/core";
import { type QueryClient, useMutation } from "@tanstack/react-query";
import { screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { expect, test, vi } from "vitest";
import { useSecretMutation } from "../api/secretMutation";
import { renderWithProviders } from "../test/render";
import { SecretReveal } from "./SecretReveal";

const SECRET = "s3cr3t-c0de-only-shown-once";

function renderReveal(props: Partial<Parameters<typeof SecretReveal>[0]> = {}) {
  const onDone = vi.fn();
  const view = renderWithProviders(
    <SecretReveal
      opened={true}
      title="Invite created"
      secrets={[{ label: "Invite code", value: SECRET }]}
      onDone={onDone}
      {...props}
    />,
  );
  return { ...view, onDone };
}

test("Escape and an outside click don't close it", async () => {
  const { user, onDone } = renderReveal();
  const dialog = await screen.findByRole("dialog");
  await user.keyboard("{Escape}");
  await user.click(document.body);
  expect(screen.getByRole("dialog")).toBe(dialog);
  expect(onDone).not.toHaveBeenCalled();
  expect(
    within(dialog).queryByRole("button", { name: /close/i }),
  ).not.toBeInTheDocument();
});

test("Done is disabled until the checkbox is ticked", async () => {
  const { user, onDone } = renderReveal();
  const dialog = within(await screen.findByRole("dialog"));
  const done = dialog.getByRole("button", { name: "Done" });
  expect(done).toBeDisabled();
  await user.click(dialog.getByLabelText("I've saved it somewhere safe"));
  expect(done).toBeEnabled();
  await user.click(done);
  expect(onDone).toHaveBeenCalledOnce();
});

test("shows each secret, the link and the warning", async () => {
  renderReveal({
    secrets: [
      { label: "OTA secret", value: "ota-value" },
      { label: "Device token", value: "token-value" },
    ],
    link: { label: "Invite link", value: "https://boop.example/invite#code=x" },
    warning: <p>This link only works on this computer.</p>,
  });
  const dialog = within(await screen.findByRole("dialog"));
  expect(dialog.getByLabelText("OTA secret")).toHaveValue("ota-value");
  expect(dialog.getByLabelText("Device token")).toHaveValue("token-value");
  expect(dialog.getByLabelText("Invite link")).toHaveValue(
    "https://boop.example/invite#code=x",
  );
  expect(dialog.getByLabelText("OTA secret")).toHaveAttribute("readonly");
  expect(
    dialog.getByText("This link only works on this computer."),
  ).toBeInTheDocument();
});

test("the copy button copies the value", async () => {
  const { user } = renderReveal();
  const dialog = within(await screen.findByRole("dialog"));
  await user.click(dialog.getByRole("button", { name: "Copy: Invite code" }));
  expect(await navigator.clipboard.readText()).toBe(SECRET);
  expect(
    dialog.getByRole("button", { name: "Copied: Invite code" }),
  ).toBeInTheDocument();
});

test("the checkbox starts unticked each time it opens", async () => {
  function Harness() {
    const [opened, setOpened] = useState(true);
    return (
      <>
        <button type="button" onClick={() => setOpened(true)}>
          Reopen
        </button>
        <SecretReveal
          opened={opened}
          title="Invite created"
          secrets={[{ label: "Invite code", value: SECRET }]}
          onDone={() => setOpened(false)}
        />
      </>
    );
  }
  const { user } = renderWithProviders(<Harness />);
  await user.click(
    await screen.findByLabelText("I've saved it somewhere safe"),
  );
  await user.click(screen.getByRole("button", { name: "Done" }));
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
  await user.click(screen.getByRole("button", { name: "Reopen" }));
  expect(
    await screen.findByLabelText("I've saved it somewhere safe"),
  ).not.toBeChecked();
});

// The flow every secret-returning mutation follows.

function cacheText(client: QueryClient): string {
  return JSON.stringify([
    client
      .getQueryCache()
      .getAll()
      .map((query) => query.state),
    client
      .getMutationCache()
      .getAll()
      .map((mutation) => mutation.state),
  ]);
}

function IssueFlow({ useHook }: { useHook: typeof useSecretMutation }) {
  const issue = useHook({
    mutationFn: () => Promise.resolve({ code: SECRET }),
  });
  return (
    <>
      <Button onClick={() => issue.mutate()}>Issue</Button>
      <SecretReveal
        opened={issue.isSuccess}
        title="Invite created"
        secrets={
          issue.data ? [{ label: "Invite code", value: issue.data.code }] : []
        }
        onDone={() => issue.reset()}
      />
    </>
  );
}

async function runFlow(useHook: typeof useSecretMutation) {
  const view = renderWithProviders(<IssueFlow useHook={useHook} />);
  const { user, queryClient } = view;
  await user.click(screen.getByRole("button", { name: "Issue" }));
  const dialog = within(await screen.findByRole("dialog"));
  expect(dialog.getByLabelText("Invite code")).toHaveValue(SECRET);
  expect(cacheText(queryClient)).toContain(SECRET);
  await user.click(dialog.getByLabelText("I've saved it somewhere safe"));
  await user.click(dialog.getByRole("button", { name: "Done" }));
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
  return queryClient;
}

test("after the flow no cache holds the secret", async () => {
  const queryClient = await runFlow(useSecretMutation);
  await waitFor(() => expect(cacheText(queryClient)).not.toContain(SECRET));
  expect(document.body.textContent).not.toContain(SECRET);
});

test("a plain mutation would keep the secret, which is why the rule exists", async () => {
  const queryClient = await runFlow(useMutation);
  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(cacheText(queryClient)).toContain(SECRET);
});
