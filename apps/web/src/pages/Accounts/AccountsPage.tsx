import { useMemo, useRef, useState, type ChangeEvent, type ReactElement } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Download,
  KeyRound,
  LogIn,
  MoreHorizontal,
  Play,
  Plus,
  ShieldCheck,
  Square,
  Upload,
  UsersRound,
} from 'lucide-react';
import { toast } from 'sonner';
import { StorageStateSchema, type Account, type AccountStatus, type LoginStatus } from '@fb/shared';
import { ACCOUNT_STATUSES, LOGIN_STATUSES } from '@fb/shared';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { AccountStatusDot, LOGIN_LABELS, LoginStatusDot } from '@/components/common/StatusDot';
import { EmptyState, ErrorNotice, errorMessage } from '@/components/common/Feedback';
import { PageHeader } from '@/components/common/PageHeader';
import { DataTable, type Column } from '@/components/tables/DataTable';
import { NativeSelect } from '@/components/forms/Field';
import { AccountFormDialog } from '../../features/accounts/components/AccountFormDialog';
import { ImportRosterDialog } from '../../features/accounts/components/ImportRosterDialog';
import {
  fetchAllAccounts,
  useAccounts,
  useCheckLoginAccounts,
  useDeleteAccount,
  useImportSession,
  useLoginAccounts,
  useSetAccountEnabled,
  useStartBrowser,
  useStopBrowser,
} from '../../features/accounts/hooks';
import { useFetchGroups } from '../../features/groups/hooks';
import { useCreateJobs } from '../../features/queue/hooks';
import { exportSession } from '../../api/accounts';
import { relativeTime } from '../../lib/format';

const STATUS_OPTIONS = [
  { value: '', label: 'Any browser state' },
  ...ACCOUNT_STATUSES.map((status) => ({ value: status, label: status })),
];

const LOGIN_OPTIONS = [
  { value: '', label: 'Any login state' },
  ...LOGIN_STATUSES.map((status) => ({ value: status, label: LOGIN_LABELS[status] })),
];

const RUNNING: readonly AccountStatus[] = ['starting', 'online', 'busy'];
const PAGE_SIZE = 100;

export const AccountsPage = (): ReactElement => {
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState('');
  const status = params.get('status') ?? '';
  const loginStatus = params.get('login') ?? '';
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [editing, setEditing] = useState<Account | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [deleting, setDeleting] = useState<Account | null>(null);
  const sessionFile = useRef<HTMLInputElement>(null);
  const [sessionTarget, setSessionTarget] = useState<string | null>(null);

  const filter = useMemo(
    () => ({
      ...(search.trim() === '' ? {} : { search: search.trim() }),
      ...(status === '' ? {} : { status: status as AccountStatus }),
      ...(loginStatus === '' ? {} : { loginStatus: loginStatus as LoginStatus }),
    }),
    [search, status, loginStatus],
  );
  const page = Math.max(1, Number(params.get('page')) || 1);
  const pageQuery = useMemo(
    () => ({ ...filter, limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE }),
    [filter, page],
  );

  const accounts = useAccounts(pageQuery);
  const startBrowser = useStartBrowser();
  const stopBrowser = useStopBrowser();
  const setEnabled = useSetAccountEnabled();
  const remove = useDeleteAccount();
  const login = useLoginAccounts();
  const checkLogin = useCheckLoginAccounts();
  const fetchGroups = useFetchGroups();
  const createJobs = useCreateJobs();
  const importSession = useImportSession();

  const rows = accounts.data?.items ?? [];
  const total = accounts.data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const visibleIds = rows.map((account) => account.id);
  // Selection is kept across pages; the bulk buttons act on all of it.
  const chosen = [...selected];
  const allVisibleChosen = visibleIds.length > 0 && visibleIds.every((id) => selected.has(id));
  const [selectingAll, setSelectingAll] = useState(false);

  const setParam = (key: string, value: string): void => {
    const next = new URLSearchParams(params);
    if (value === '') next.delete(key);
    else next.set(key, value);
    // A new filter starts from the first page; the old page number means nothing now.
    if (key !== 'page') next.delete('page');
    setParams(next, { replace: true });
  };

  const changeSearch = (value: string): void => {
    setSearch(value);
    if (params.has('page')) setParam('page', '');
  };

  /** Every account the current filter matches, on every page. */
  const selectAllMatching = async (): Promise<void> => {
    setSelectingAll(true);
    try {
      const all = await fetchAllAccounts(filter);
      setSelected(new Set(all.map((account) => account.id)));
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setSelectingAll(false);
    }
  };

  const toggle = (id: string): void =>
    setSelected((state) => {
      const next = new Set(state);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const fail = (error: unknown): void => {
    toast.error(errorMessage(error));
  };

  const queued = (what: string) => (jobs: { length: number }) =>
    toast.success(`Queued ${what} for ${jobs.length} account${jobs.length === 1 ? '' : 's'}`);

  const bulk = (accountIds: string[]) => ({
    login: () =>
      login.mutate(
        { accountIds, waitForOperator: true },
        { onError: fail, onSuccess: queued('login') },
      ),
    checkLogin: () =>
      checkLogin.mutate(accountIds, { onError: fail, onSuccess: queued('a login check') }),
    fetchGroups: () =>
      fetchGroups.mutate(accountIds, { onError: fail, onSuccess: queued('a group fetch') }),
    acceptRequests: () =>
      createJobs.mutate(
        { accountIds, action: { type: 'accept_friend_requests', max: 100 } },
        { onError: fail, onSuccess: (result) => queued('accepting requests')(result.jobs) },
      ),
    autoSetup: () =>
      createJobs.mutate(
        { accountIds, action: { type: 'auto_setup_profile' } },
        { onError: fail, onSuccess: (result) => queued('profile setup')(result.jobs) },
      ),
  });

  const downloadSession = async (account: Account): Promise<void> => {
    try {
      const session = await exportSession(account.id);
      const blob = new Blob([JSON.stringify(session, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `session-${account.name}.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      toast.success(`Session exported for ${account.displayName}`);
    } catch (error) {
      fail(error);
    }
  };

  const chooseSessionFile = (account: Account): void => {
    setSessionTarget(account.id);
    sessionFile.current?.click();
  };

  const uploadSession = async (event: ChangeEvent<HTMLInputElement>): Promise<void> => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (file === undefined || sessionTarget === null) return;

    try {
      const raw: unknown = JSON.parse(await file.text());
      const candidate =
        typeof raw === 'object' && raw !== null && 'state' in raw
          ? (raw as { state: unknown }).state
          : raw;
      const state = StorageStateSchema.parse(candidate);
      importSession.mutate(
        { id: sessionTarget, state },
        {
          onError: fail,
          onSuccess: () => toast.success('Session imported; run a login check to confirm it'),
        },
      );
    } catch {
      toast.error('That file is not an exported session');
    }
  };

  const columns: ReadonlyArray<Column<Account>> = [
    {
      key: 'select',
      header: '',
      width: '36px',
      render: (account) => (
        <Checkbox
          checked={selected.has(account.id)}
          onCheckedChange={() => toggle(account.id)}
          aria-label={`Select ${account.displayName}`}
        />
      ),
    },
    {
      key: 'no',
      header: '#',
      width: '48px',
      secondary: true,
      render: (account) => (
        <span className="tabular text-muted-foreground">{account.sheetNo ?? '—'}</span>
      ),
    },
    {
      key: 'name',
      header: 'Account',
      render: (account) => (
        <div className="grid">
          <span className="flex items-center gap-2 font-medium">
            {account.facebookName ?? account.displayName}
            {!account.enabled && <Badge variant="outline">Disabled</Badge>}
          </span>
          {(account.username !== null || account.name !== account.displayName) && (
            <span className="truncate text-xs text-muted-foreground">
              {account.username ?? account.name}
            </span>
          )}
        </div>
      ),
    },
    {
      key: 'login',
      header: 'Login',
      width: '150px',
      render: (account) => (
        <div className="grid gap-0.5">
          <LoginStatusDot status={account.loginStatus} />
          {account.loginReason !== null && (
            <span className="truncate text-xs text-muted-foreground" title={account.loginReason}>
              {account.loginReason}
            </span>
          )}
        </div>
      ),
    },
    {
      key: 'status',
      header: 'Browser',
      width: '120px',
      render: (account) => <AccountStatusDot status={account.status} />,
    },
    {
      key: 'checked',
      header: 'Checked',
      width: '130px',
      secondary: true,
      render: (account) => (
        <span className="text-muted-foreground">
          {account.lastLoginCheckAt === null ? '—' : relativeTime(account.lastLoginCheckAt)}
        </span>
      ),
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      width: '210px',
      render: (account) => {
        const running = RUNNING.includes(account.status);
        const one = bulk([account.id]);

        return (
          <div className="flex justify-end gap-1.5">
            {running ? (
              <Button
                size="sm"
                variant="outline"
                onClick={() => stopBrowser.mutate(account.id, { onError: fail })}
                disabled={stopBrowser.isPending && stopBrowser.variables === account.id}
              >
                <Square /> Stop
              </Button>
            ) : (
              <Button
                size="sm"
                disabled={
                  !account.enabled ||
                  (startBrowser.isPending && startBrowser.variables === account.id)
                }
                onClick={() =>
                  startBrowser.mutate(account.id, {
                    onError: fail,
                    onSuccess: () => toast.success(`Browser started for ${account.displayName}`),
                  })
                }
              >
                <Play /> Browser
              </Button>
            )}

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  size="icon-sm"
                  variant="ghost"
                  aria-label={`More actions for ${account.displayName}`}
                >
                  <MoreHorizontal />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={one.login} disabled={!account.hasPassword}>
                  <LogIn /> Log in
                </DropdownMenuItem>
                <DropdownMenuItem onClick={one.checkLogin}>
                  <ShieldCheck /> Check login
                </DropdownMenuItem>
                <DropdownMenuItem onClick={one.fetchGroups}>
                  <UsersRound /> Fetch groups
                </DropdownMenuItem>
                <DropdownMenuItem onClick={one.acceptRequests}>
                  Accept friend requests
                </DropdownMenuItem>
                <DropdownMenuItem onClick={one.autoSetup}>Auto-set up the profile</DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => void downloadSession(account)} disabled={running}>
                  <Download /> Export session
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => chooseSessionFile(account)} disabled={running}>
                  <Upload /> Import session
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onClick={() => {
                    setEditing(account);
                    setDialogOpen(true);
                  }}
                >
                  <KeyRound /> Edit
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() =>
                    setEnabled.mutate(
                      { id: account.id, enabled: !account.enabled },
                      { onError: fail },
                    )
                  }
                >
                  {account.enabled ? 'Disable' : 'Enable'}
                </DropdownMenuItem>
                <DropdownMenuItem
                  className="text-destructive focus:text-destructive"
                  onClick={() => setDeleting(account)}
                >
                  Delete
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        );
      },
    },
  ];

  const filtered = search !== '' || status !== '' || loginStatus !== '';
  const many = bulk(chosen);

  return (
    <div className="grid gap-6">
      <PageHeader
        title="Accounts"
        description="The roster. Every account owns one persistent browser profile; sign in once and the profile keeps the session."
        actions={
          <>
            <Button variant="outline" onClick={() => setImportOpen(true)}>
              <Upload /> Import roster
            </Button>
            <Button
              onClick={() => {
                setEditing(null);
                setDialogOpen(true);
              }}
            >
              <Plus /> Add account
            </Button>
          </>
        }
      />

      <div className="flex flex-wrap gap-3">
        <Input
          aria-label="Search"
          placeholder="Search name, username, email"
          value={search}
          onChange={(event) => changeSearch(event.target.value)}
          className="w-full sm:max-w-xs"
        />
        <NativeSelect
          aria-label="Login state"
          value={loginStatus}
          options={LOGIN_OPTIONS}
          onChange={(event) => setParam('login', event.target.value)}
          className="w-full sm:w-48"
        />
        <NativeSelect
          aria-label="Browser state"
          value={status}
          options={STATUS_OPTIONS}
          onChange={(event) => setParam('status', event.target.value)}
          className="w-full sm:w-48"
        />
      </div>

      {rows.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border bg-card px-3 py-2">
          <Checkbox
            checked={allVisibleChosen}
            onCheckedChange={(value) =>
              setSelected((state) => {
                const next = new Set(state);
                for (const id of visibleIds) {
                  if (value === true) next.add(id);
                  else next.delete(id);
                }
                return next;
              })
            }
            aria-label="Select every account on this page"
          />
          <span className="text-sm text-muted-foreground">
            {chosen.length === 0
              ? 'Select accounts to act on them together'
              : `${chosen.length} selected`}
          </span>
          {total > visibleIds.length && chosen.length < total && (
            <Button
              size="xs"
              variant="link"
              disabled={selectingAll}
              onClick={() => void selectAllMatching()}
            >
              Select all {total}
            </Button>
          )}
          {chosen.length > 0 && (
            <Button size="xs" variant="link" onClick={() => setSelected(new Set())}>
              Clear
            </Button>
          )}
          <div className="ml-auto flex flex-wrap gap-1.5">
            <Button size="sm" variant="outline" disabled={chosen.length === 0} onClick={many.login}>
              <LogIn /> Log in
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={chosen.length === 0}
              onClick={many.checkLogin}
            >
              <ShieldCheck /> Check login
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={chosen.length === 0}
              onClick={many.fetchGroups}
            >
              <UsersRound /> Fetch groups
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={chosen.length === 0}
              onClick={many.acceptRequests}
            >
              Accept requests
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={chosen.length === 0}
              onClick={many.autoSetup}
            >
              Auto-set up
            </Button>
          </div>
        </div>
      )}

      {accounts.isError && <ErrorNotice error={accounts.error} />}

      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(account) => account.id}
        loading={accounts.isFetching}
        empty={
          <EmptyState
            title={filtered ? 'Nothing matches' : 'No accounts yet'}
            description={
              filtered
                ? 'Try a different search or filter.'
                : 'Import the roster from the Google Sheet, or add an account by hand.'
            }
            action={
              filtered ? undefined : (
                <div className="flex gap-2">
                  <Button variant="outline" onClick={() => setImportOpen(true)}>
                    <Upload /> Import roster
                  </Button>
                  <Button
                    onClick={() => {
                      setEditing(null);
                      setDialogOpen(true);
                    }}
                  >
                    <Plus /> Add account
                  </Button>
                </div>
              )
            }
          />
        }
      />

      {total > PAGE_SIZE && (
        <nav className="flex items-center justify-between gap-3 text-sm" aria-label="Pages">
          <span className="text-muted-foreground">
            {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, total)} of {total}
          </span>
          <div className="flex gap-1.5">
            <Button
              size="sm"
              variant="outline"
              disabled={page <= 1}
              onClick={() => setParam('page', page <= 2 ? '' : String(page - 1))}
            >
              Previous
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={page >= pageCount}
              onClick={() => setParam('page', String(page + 1))}
            >
              Next
            </Button>
          </div>
        </nav>
      )}

      <input
        ref={sessionFile}
        type="file"
        accept="application/json"
        className="sr-only"
        aria-label="Session file"
        onChange={(event) => void uploadSession(event)}
      />

      <AccountFormDialog open={dialogOpen} account={editing} onClose={() => setDialogOpen(false)} />
      <ImportRosterDialog open={importOpen} onClose={() => setImportOpen(false)} />

      <Dialog open={deleting !== null} onOpenChange={(open) => !open && setDeleting(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete {deleting?.displayName}?</DialogTitle>
            <DialogDescription>
              Its jobs, groups and browser profile are removed with it. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleting(null)}>
              Keep it
            </Button>
            <Button
              variant="destructive"
              disabled={remove.isPending}
              onClick={() => {
                if (deleting === null) return;
                remove.mutate(deleting.id, {
                  onError: fail,
                  onSuccess: () => {
                    toast.success(`Deleted ${deleting.displayName}`);
                    setDeleting(null);
                  },
                });
              }}
            >
              Delete account
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
