import type { ReactElement, ReactNode } from 'react';
import './DataTable.css';

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  /** Narrow columns stay narrow when the table has room to spare. */
  width?: string;
  align?: 'left' | 'right';
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
  if (!loading && rows.length === 0) return <div className="table-empty">{empty}</div>;

  return (
    <div className="table-wrap" aria-busy={loading}>
      <table className="table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                style={column.width === undefined ? undefined : { width: column.width }}
                className={column.align === 'right' ? 'table__cell--right' : undefined}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={column.align === 'right' ? 'table__cell--right' : undefined}
                >
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
