import { Title } from "@mantine/core";

export function PagePlaceholder({ title }: { title: string }) {
  return <Title order={1}>{title}</Title>;
}
