import { useMemo, useState, type ReactElement } from 'react';
import { LOG_LEVELS, type LogEntry, type LogLevel } from '@fb/shared';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { LogLevelDot } from '@/components/common/StatusDot';
import { EmptyState, ErrorNotice } from '@/components/common/Feedback';
import { PageHeader } from '@/components/common/PageHeader';
import { NativeSelect } from '@/components/forms/Field';
import { DataTable, type Column } from '@/components/tables/DataTable';
import { useAllAccounts } from '../../features/accounts/hooks';
import { useLogs } from '../../features/monitoring/hooks';
import { clockTime, dateTime } from '../../lib/format';

const PAGE_SIZE = 100;

export const LogsPage = (): ReactElement => {
  const [level, setLevel] = useState('');
  const [accountId, setAccountId] = useState('');
  const [search, setSearch] = useState('');
  const [from, setFrom] = useState('');
  const [page, setPage] = useState(0);

  const accounts = useAllAccounts();

  const query = useMemo(
    () => ({
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
      ...(level === '' ? {} : { level: [level as LogLevel] }),
      ...(accountId === '' ? {} : { accountId }),
      ...(search.trim() === '' ? {} : { search: search.trim() }),
      ...(from === '' ? {} : { from: new Date(from).toISOString() }),
    }),
    [level, accountId, search, from, page],
  );

  const logs = useLogs(query);
  const total = logs.data?.total ?? 0;
  const lastPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1);

  const accountOptions = [
    { value: '', label: 'Any account' },
    ...(accounts.data ?? []).map((account) => ({
      value: account.id,
      label: account.displayName,
    })),
  ];

  const columns: ReadonlyArray<Column<LogEntry>> = [
    {
      key: 'time',
      header: 'Time',
      width: '96px',
      render: (entry) => (
        <span title={dateTime(entry.createdAt)} className="font-mono text-xs text-muted-foreground">
          {clockTime(entry.createdAt)}
        </span>
      ),
    },
    {
      key: 'level',
      header: 'Level',
      width: '100px',
      render: (entry) => <LogLevelDot level={entry.level} />,
    },
    {
      key: 'event',
      header: 'Event',
      width: '190px',
      secondary: true,
      render: (entry) => (
        <span className="font-mono text-xs">
          {entry.event ?? <span className="text-muted-foreground">—</span>}
        </span>
      ),
    },
    { key: 'message', header: 'Message', render: (entry) => entry.message },
    {
      key: 'context',
      header: 'Context',
      width: '220px',
      secondary: true,
      render: (entry) => (
        <span className="grid font-mono text-xs text-muted-foreground">
          {entry.accountId !== null && <span>{entry.accountId}</span>}
          {entry.jobId !== null && <span>{entry.jobId}</span>}
        </span>
      ),
    },
  ];

  const resetPageAnd = (apply: () => void): void => {
    setPage(0);
    apply();
  };

  return (
    <div className="grid gap-6">
      <PageHeader
        title="Logs"
        description="Everything the server wrote, with credentials already removed."
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <NativeSelect
          aria-label="Level"
          value={level}
          options={[
            { value: '', label: 'Any level' },
            ...LOG_LEVELS.map((value) => ({ value, label: value })),
          ]}
          onChange={(event) => resetPageAnd(() => setLevel(event.target.value))}
        />
        <NativeSelect
          aria-label="Account"
          value={accountId}
          options={accountOptions}
          onChange={(event) => resetPageAnd(() => setAccountId(event.target.value))}
        />
        <Input
          aria-label="Search"
          placeholder="Search the message"
          value={search}
          onChange={(event) => resetPageAnd(() => setSearch(event.target.value))}
        />
        <Input
          aria-label="From"
          type="datetime-local"
          value={from}
          onChange={(event) => resetPageAnd(() => setFrom(event.target.value))}
        />
      </div>

      {logs.isError && <ErrorNotice error={logs.error} />}

      <DataTable
        columns={columns}
        rows={logs.data?.items ?? []}
        rowKey={(entry) => entry.id}
        loading={logs.isFetching}
        empty={
          <EmptyState title="No log entries match" description="Widen the filters to see more." />
        }
      />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="text-sm text-muted-foreground">
          {total === 0 ? 'Nothing to show' : `${total} entr${total === 1 ? 'y' : 'ies'}`}
        </span>
        <div className="flex gap-2">
          <Button
            size="sm"
            variant="outline"
            disabled={page === 0}
            onClick={() => setPage((value) => value - 1)}
          >
            Previous
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={page >= lastPage}
            onClick={() => setPage((value) => value + 1)}
          >
            Next
          </Button>
        </div>
      </div>
    </div>
  );
};
