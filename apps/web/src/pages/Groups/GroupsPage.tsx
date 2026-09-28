import { useMemo, useState, type ReactElement } from 'react';
import { RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import type { GroupSummary } from '@fb/shared';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { EmptyState, ErrorNotice, errorMessage } from '@/components/common/Feedback';
import { PageHeader } from '@/components/common/PageHeader';
import { DataTable, type Column } from '@/components/tables/DataTable';
import { NativeSelect } from '@/components/forms/Field';
import { useAccounts } from '../../features/accounts/hooks';
import { useFetchGroups, useGroupSummaries } from '../../features/groups/hooks';

/**
 * Every group any account belongs to, as last read from Facebook, with the
 * accounts that can share into it. Fetching is a job per account; the table
 * fills in as each finishes.
 */
export const GroupsPage = (): ReactElement => {
  const [search, setSearch] = useState('');
  const [accountId, setAccountId] = useState('');

  const accounts = useAccounts({ limit: 200 });
  const summaries = useGroupSummaries();
  const fetch = useFetchGroups();

  const accountName = useMemo(
    () => new Map((accounts.data?.items ?? []).map((account) => [account.id, account.displayName])),
    [accounts.data],
  );

  const rows = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return (summaries.data ?? []).filter(
      (group) =>
        (needle === '' ||
          group.name.toLowerCase().includes(needle) ||
          group.url.includes(needle)) &&
        (accountId === '' || group.accountIds.includes(accountId)),
    );
  }, [summaries.data, search, accountId]);

  const fetchAll = (): void => {
    const ids = (accounts.data?.items ?? [])
      .filter((account) => account.enabled)
      .map((account) => account.id);
    if (ids.length === 0) {
      toast.error('No enabled accounts to fetch groups for');
      return;
    }
    fetch.mutate(ids, {
      onError: (error) => toast.error(errorMessage(error)),
      onSuccess: (jobs) =>
        toast.success(
          `Queued a group fetch for ${jobs.length} account${jobs.length === 1 ? '' : 's'}`,
        ),
    });
  };

  const columns: ReadonlyArray<Column<GroupSummary>> = [
    {
      key: 'name',
      header: 'Group',
      render: (group) => (
        <div className="grid">
          <span className="font-medium">{group.name}</span>
          <a
            href={group.url}
            target="_blank"
            rel="noreferrer"
            className="truncate font-mono text-xs text-muted-foreground hover:underline"
          >
            {group.url}
          </a>
        </div>
      ),
    },
    {
      key: 'accounts',
      header: 'Accounts in it',
      width: '120px',
      render: (group) => <span className="tabular">{group.accountIds.length}</span>,
    },
    {
      key: 'members',
      header: 'Which',
      secondary: true,
      render: (group) => (
        <span className="text-muted-foreground">
          {group.accountIds
            .map((id) => accountName.get(id) ?? id)
            .slice(0, 4)
            .join(', ')}
          {group.accountIds.length > 4 ? ` +${group.accountIds.length - 4}` : ''}
        </span>
      ),
    },
  ];

  return (
    <div className="grid gap-6">
      <PageHeader
        title="Groups"
        description="Groups the accounts belong to, read from Facebook. Compose uses this list to pick where a post is shared."
        actions={
          <Button onClick={fetchAll} disabled={fetch.isPending}>
            <RefreshCw /> Fetch from Facebook
          </Button>
        }
      />

      <div className="flex flex-wrap gap-3">
        <Input
          aria-label="Search"
          placeholder="Search by name or URL"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          className="w-full sm:max-w-xs"
        />
        <NativeSelect
          aria-label="Account"
          value={accountId}
          options={[
            { value: '', label: 'Any account' },
            ...(accounts.data?.items ?? []).map((account) => ({
              value: account.id,
              label: account.displayName,
            })),
          ]}
          onChange={(event) => setAccountId(event.target.value)}
          className="w-full sm:w-56"
        />
      </div>

      {summaries.isError && <ErrorNotice error={summaries.error} />}

      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(group) => group.url}
        loading={summaries.isFetching}
        empty={
          <EmptyState
            title={summaries.data?.length === 0 ? 'No groups fetched yet' : 'Nothing matches'}
            description={
              summaries.data?.length === 0
                ? 'Fetch from Facebook to read each signed-in account’s groups.'
                : 'Try a different search or account.'
            }
            action={
              summaries.data?.length === 0 ? (
                <Button onClick={fetchAll}>
                  <RefreshCw /> Fetch from Facebook
                </Button>
              ) : undefined
            }
          />
        }
      />
    </div>
  );
};
