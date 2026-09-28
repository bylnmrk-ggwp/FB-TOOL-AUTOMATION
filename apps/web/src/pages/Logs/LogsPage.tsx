import { useMemo, useState, type ReactElement } from 'react';
import { LOG_LEVELS, type LogEntry, type LogLevel } from '@fb/shared';
import { LogLevelBadge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { EmptyState, ErrorNotice } from '../../components/ui/Feedback';
import { PageHeader } from '../../components/ui/PageHeader';
import { SelectField, TextField } from '../../components/forms/Field';
import { DataTable, type Column } from '../../components/tables/DataTable';
import { useAccounts } from '../../features/accounts/hooks';
import { useLogs } from '../../features/monitoring/hooks';
import { clockTime, dateTime } from '../../lib/format';
import './LogsPage.css';

const PAGE_SIZE = 100;

export const LogsPage = (): ReactElement => {
  const [level, setLevel] = useState('');
  const [accountId, setAccountId] = useState('');
  const [search, setSearch] = useState('');
  const [from, setFrom] = useState('');
  const [page, setPage] = useState(0);

  const accounts = useAccounts({ limit: 200 });

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
    ...(accounts.data?.items ?? []).map((account) => ({
      value: account.id,
      label: account.displayName,
    })),
  ];

  const columns: ReadonlyArray<Column<LogEntry>> = [
    {
      key: 'time',
      header: 'Time',
      width: '110px',
      render: (entry) => (
        <span title={dateTime(entry.createdAt)} className="mono">
          {clockTime(entry.createdAt)}
        </span>
      ),
    },
    {
      key: 'level',
      header: 'Level',
      width: '90px',
      render: (entry) => <LogLevelBadge level={entry.level} />,
    },
    {
      key: 'event',
      header: 'Event',
      width: '180px',
      render: (entry) => <span className="mono">{entry.event ?? '—'}</span>,
    },
    { key: 'message', header: 'Message', render: (entry) => entry.message },
    {
      key: 'context',
      header: 'Context',
      width: '220px',
      render: (entry) => (
        <span className="logs__context">
          {entry.accountId !== null && <span className="mono">{entry.accountId}</span>}
          {entry.jobId !== null && <span className="mono">{entry.jobId}</span>}
        </span>
      ),
    },
  ];

  const resetPageAnd = (apply: () => void): void => {
    setPage(0);
    apply();
  };

  return (
    <div className="page">
      <PageHeader
        title="Logs"
        description="Everything the server wrote, with credentials already removed."
      />

      <div className="logs__filters">
        <SelectField
          label="Level"
          value={level}
          options={[
            { value: '', label: 'Any level' },
            ...LOG_LEVELS.map((value) => ({ value, label: value })),
          ]}
          onChange={(event) => resetPageAnd(() => setLevel(event.target.value))}
        />
        <SelectField
          label="Account"
          value={accountId}
          options={accountOptions}
          onChange={(event) => resetPageAnd(() => setAccountId(event.target.value))}
        />
        <TextField
          label="Search"
          placeholder="Search the message"
          value={search}
          onChange={(event) => resetPageAnd(() => setSearch(event.target.value))}
        />
        <TextField
          label="From"
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
        empty={<EmptyState title="No log entries match" />}
      />

      <div className="logs__pager">
        <span className="muted">
          {total === 0 ? 'Nothing to show' : `${total} entr${total === 1 ? 'y' : 'ies'}`}
        </span>
        <div className="row">
          <Button size="sm" disabled={page === 0} onClick={() => setPage((value) => value - 1)}>
            Previous
          </Button>
          <Button
            size="sm"
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
