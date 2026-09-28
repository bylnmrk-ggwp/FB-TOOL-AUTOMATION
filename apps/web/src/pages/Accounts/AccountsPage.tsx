import { useMemo, useState, type ReactElement } from 'react';
import type { Account, AccountStatus } from '@fb/shared';
import { ACCOUNT_STATUSES } from '@fb/shared';
import { AccountStatusBadge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { EmptyState, ErrorNotice } from '../../components/ui/Feedback';
import { PageHeader } from '../../components/ui/PageHeader';
import { DataTable, type Column } from '../../components/tables/DataTable';
import { TextField, SelectField } from '../../components/forms/Field';
import { AccountFormDialog } from '../../features/accounts/components/AccountFormDialog';
import {
  useAccounts,
  useDeleteAccount,
  useSetAccountEnabled,
  useStartBrowser,
  useStopBrowser,
} from '../../features/accounts/hooks';
import { relativeTime } from '../../lib/format';
import './AccountsPage.css';

const STATUS_OPTIONS = [
  { value: '', label: 'Any status' },
  ...ACCOUNT_STATUSES.map((status) => ({ value: status, label: status })),
];

const RUNNING: readonly AccountStatus[] = ['starting', 'online', 'busy'];

export const AccountsPage = (): ReactElement => {
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [editing, setEditing] = useState<Account | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  const query = useMemo(
    () => ({
      limit: 100,
      ...(search.trim() === '' ? {} : { search: search.trim() }),
      ...(status === '' ? {} : { status: status as AccountStatus }),
    }),
    [search, status],
  );

  const accounts = useAccounts(query);
  const startBrowser = useStartBrowser();
  const stopBrowser = useStopBrowser();
  const setEnabled = useSetAccountEnabled();
  const remove = useDeleteAccount();

  const actionError = startBrowser.error ?? stopBrowser.error ?? setEnabled.error ?? remove.error;

  const openCreate = (): void => {
    setEditing(null);
    setDialogOpen(true);
  };

  const openEdit = (account: Account): void => {
    setEditing(account);
    setDialogOpen(true);
  };

  const confirmDelete = (account: Account): void => {
    const confirmed = window.confirm(
      `Delete ${account.name}? Its jobs and its browser profile are removed too. This cannot be undone.`,
    );
    if (confirmed) remove.mutate(account.id);
  };

  const columns: ReadonlyArray<Column<Account>> = [
    {
      key: 'name',
      header: 'Account',
      render: (account) => (
        <div className="accounts__name">
          <span>{account.displayName}</span>
          {account.displayName !== account.name && (
            <span className="accounts__secondary">{account.name}</span>
          )}
        </div>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      width: '120px',
      render: (account) => <AccountStatusBadge status={account.status} />,
    },
    {
      key: 'enabled',
      header: 'Enabled',
      width: '110px',
      render: (account) => (account.enabled ? 'Yes' : 'No'),
    },
    {
      key: 'lastActive',
      header: 'Last active',
      width: '150px',
      render: (account) =>
        account.lastActiveAt === null ? '—' : relativeTime(account.lastActiveAt),
    },
    {
      key: 'error',
      header: 'Last error',
      render: (account) =>
        account.lastError === null ? (
          '—'
        ) : (
          <span className="accounts__error" title={account.lastError}>
            {account.lastError}
          </span>
        ),
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'right',
      width: '320px',
      render: (account) => {
        const running = RUNNING.includes(account.status);

        return (
          <div className="accounts__actions">
            {running ? (
              <Button
                size="sm"
                onClick={() => stopBrowser.mutate(account.id)}
                loading={stopBrowser.isPending && stopBrowser.variables === account.id}
              >
                Stop browser
              </Button>
            ) : (
              <Button
                size="sm"
                variant="primary"
                disabled={!account.enabled}
                onClick={() => startBrowser.mutate(account.id)}
                loading={startBrowser.isPending && startBrowser.variables === account.id}
              >
                Start browser
              </Button>
            )}

            <Button
              size="sm"
              variant="ghost"
              onClick={() => setEnabled.mutate({ id: account.id, enabled: !account.enabled })}
            >
              {account.enabled ? 'Disable' : 'Enable'}
            </Button>

            <Button size="sm" variant="ghost" onClick={() => openEdit(account)}>
              Edit
            </Button>

            <Button size="sm" variant="danger" onClick={() => confirmDelete(account)}>
              Delete
            </Button>
          </div>
        );
      },
    },
  ];

  return (
    <div className="page">
      <PageHeader
        title="Accounts"
        description="Every account owns one persistent browser profile."
        actions={
          <Button variant="primary" onClick={openCreate}>
            Add account
          </Button>
        }
      />

      <div className="accounts__filters">
        <TextField
          label="Search"
          placeholder="Search by name"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <SelectField
          label="Status"
          value={status}
          options={STATUS_OPTIONS}
          onChange={(event) => setStatus(event.target.value)}
        />
      </div>

      {accounts.isError && <ErrorNotice error={accounts.error} />}
      {actionError !== null && actionError !== undefined && <ErrorNotice error={actionError} />}

      <DataTable
        columns={columns}
        rows={accounts.data?.items ?? []}
        rowKey={(account) => account.id}
        loading={accounts.isFetching}
        empty={
          <EmptyState
            title={search === '' && status === '' ? 'No accounts yet' : 'Nothing matches'}
            description={
              search === '' && status === ''
                ? 'Add an account to give it a browser profile of its own.'
                : 'Try a different search or status.'
            }
            action={
              search === '' && status === '' ? (
                <Button variant="primary" onClick={openCreate}>
                  Add account
                </Button>
              ) : undefined
            }
          />
        }
      />

      <AccountFormDialog open={dialogOpen} account={editing} onClose={() => setDialogOpen(false)} />
    </div>
  );
};
