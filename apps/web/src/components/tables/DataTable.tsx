import type { ReactElement, ReactNode } from 'react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { cn } from '@/lib/utils';

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  /** Narrow columns stay narrow when the table has room to spare. */
  width?: string;
  align?: 'left' | 'right';
  /** Hidden below the `md` breakpoint so the essential columns keep their room. */
  secondary?: boolean;
}

interface DataTableProps<T> {
  columns: ReadonlyArray<Column<T>>;
  rows: readonly T[];
  rowKey: (row: T) => string;
  empty: ReactNode;
  loading?: boolean;
}

/**
 * One table for every list in the application. It renders cells and nothing
 * else — sorting, filtering and paging belong to the page, which is the only
 * place that knows what the server can do.
 */
export const DataTable = <T,>({
  columns,
  rows,
  rowKey,
  empty,
  loading = false,
}: DataTableProps<T>): ReactElement => {
  if (!loading && rows.length === 0) return <>{empty}</>;

  return (
    <div
      className={cn(
        'overflow-x-auto rounded-lg border bg-card transition-opacity',
        loading && 'opacity-60',
      )}
      aria-busy={loading}
    >
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            {columns.map((column) => (
              <TableHead
                key={column.key}
                style={column.width === undefined ? undefined : { width: column.width }}
                className={cn(
                  'h-10 text-xs font-medium text-muted-foreground',
                  column.align === 'right' && 'text-right',
                  column.secondary && 'hidden md:table-cell',
                )}
              >
                {column.header}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={rowKey(row)}>
              {columns.map((column) => (
                <TableCell
                  key={column.key}
                  className={cn(
                    'py-2.5',
                    column.align === 'right' && 'text-right',
                    column.secondary && 'hidden md:table-cell',
                  )}
                >
                  {column.render(row)}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
};
