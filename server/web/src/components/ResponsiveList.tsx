import {
  Card,
  Group,
  Stack,
  Table,
  Text,
  useMantineTheme,
} from "@mantine/core";
import { useMediaQuery } from "@mantine/hooks";
import type { Key, ReactNode } from "react";
import { Link } from "react-router";
import classes from "./ResponsiveList.module.css";

export interface Column<Row> {
  id: string;
  header: string;
  render: (row: Row) => ReactNode;
  /** The card title on phones, and the cell that holds the row link. */
  primary?: boolean;
}

interface ResponsiveListProps<Row> {
  rows: readonly Row[];
  rowKey: (row: Row) => Key;
  columns: readonly Column<Row>[];
  /**
   * Makes each row or card a real link. Columns then mustn't render their own
   * links or buttons, which would sit under the row link.
   */
  rowHref?: (row: Row) => string;
  empty: ReactNode;
}

/** A table from the `sm` breakpoint up, a stack of cards below it. */
export function ResponsiveList<Row>({
  rows,
  rowKey,
  columns,
  rowHref,
  empty,
}: ResponsiveListProps<Row>) {
  const theme = useMantineTheme();
  const wide = useMediaQuery(`(min-width: ${theme.breakpoints.sm})`, false, {
    getInitialValueInEffect: false,
  });
  if (rows.length === 0) return <>{empty}</>;

  const primary = columns.find((column) => column.primary) ?? columns[0];

  if (wide) {
    return (
      <Table highlightOnHover={rowHref !== undefined}>
        <Table.Thead>
          <Table.Tr>
            {columns.map((column) => (
              <Table.Th key={column.id}>{column.header}</Table.Th>
            ))}
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((row) => (
            <Table.Tr key={rowKey(row)} className={classes.row}>
              {columns.map((column) => (
                <Table.Td key={column.id}>
                  {rowHref && column === primary ? (
                    <Link to={rowHref(row)} className={classes.rowLink}>
                      {column.render(row)}
                    </Link>
                  ) : (
                    column.render(row)
                  )}
                </Table.Td>
              ))}
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    );
  }

  const rest = columns.filter((column) => column !== primary);
  return (
    <Stack>
      {rows.map((row) => {
        const body = (
          <>
            <Text fw={500}>{primary.render(row)}</Text>
            <Stack gap={4} mt="xs">
              {rest.map((column) => (
                <Group key={column.id} justify="space-between" wrap="nowrap">
                  <Text size="sm" c="dimmed">
                    {column.header}
                  </Text>
                  <div>{column.render(row)}</div>
                </Group>
              ))}
            </Stack>
          </>
        );
        return rowHref ? (
          <Card
            key={rowKey(row)}
            withBorder={true}
            component={Link}
            to={rowHref(row)}
            className={classes.card}
          >
            {body}
          </Card>
        ) : (
          <Card key={rowKey(row)} withBorder={true}>
            {body}
          </Card>
        );
      })}
    </Stack>
  );
}
