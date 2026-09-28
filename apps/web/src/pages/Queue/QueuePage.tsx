import { useMemo, useState, type ReactElement, type ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';
import { OctagonX, RotateCcw, XCircle } from 'lucide-react';
import { toast } from 'sonner';
import type { Job, JobStatus } from '@fb/shared';
import { JOB_STATUSES } from '@fb/shared';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { JobStatusDot } from '@/components/common/StatusDot';
import { EmptyState, ErrorNotice, errorMessage } from '@/components/common/Feedback';
import { PageHeader } from '@/components/common/PageHeader';
import { Modal } from '@/components/dialogs/Modal';
import { DataTable, type Column } from '@/components/tables/DataTable';
import { cn } from '@/lib/utils';
import { useAccounts } from '../../features/accounts/hooks';
import {
  useCancelAllJobs,
  useCancelJob,
  useJobs,
  useQueueStats,
  useRetryJob,
} from '../../features/queue/hooks';
import { useLiveStore } from '../../features/automation/liveStore';
import { dateTime, humanise, relativeTime } from '../../lib/format';

const ACTIVE: readonly JobStatus[] = ['pending', 'queued', 'running', 'retrying'];
const TERMINAL: readonly JobStatus[] = ['completed', 'failed', 'cancelled'];

type Filter = 'active' | 'finished' | JobStatus;

const isFilter = (value: string | null): value is Filter =>
  value === 'active' ||
  value === 'finished' ||
  (JOB_STATUSES as readonly string[]).includes(value ?? '');

const statusesFor = (filter: Filter): JobStatus[] => {
  if (filter === 'active') return [...ACTIVE];
  if (filter === 'finished') return [...TERMINAL];
  return [filter];
};

export const QueuePage = (): ReactElement => {
  const [params, setParams] = useSearchParams();
  const raw = params.get('filter');
  const filter: Filter = isFilter(raw) ? raw : 'active';
  const [inspecting, setInspecting] = useState<Job | null>(null);

  const jobs = useJobs(useMemo(() => ({ status: statusesFor(filter), limit: 100 }), [filter]));
  const stats = useQueueStats();
  const accounts = useAccounts({ limit: 200 });
  const cancel = useCancelJob();
  const cancelAll = useCancelAllJobs();
  const retry = useRetryJob();
  const progress = useLiveStore((state) => state.progress);

  const setFilter = (value: string): void => {
    const next = new URLSearchParams(params);
    if (value === 'active') next.delete('filter');
    else next.set('filter', value);
    setParams(next, { replace: true });
  };

  const accountName = useMemo(() => {
    const names = new Map<string, string>();
    for (const account of accounts.data?.items ?? []) names.set(account.id, account.displayName);
    return names;
  }, [accounts.data]);

  const fail = (error: unknown): void => {
    toast.error(errorMessage(error));
  };

  const activeCount =
    stats.data === undefined
      ? 1
      : stats.data.pending + stats.data.queued + stats.data.running + stats.data.retrying;

  const columns: ReadonlyArray<Column<Job>> = [
    {
      key: 'type',
      header: 'Job',
      render: (job) => (
        <button
          type="button"
          className="grid text-left hover:underline"
          onClick={() => setInspecting(job)}
        >
          <span className="font-medium">{humanise(job.type)}</span>
          <span className="text-xs text-muted-foreground">
            {accountName.get(job.accountId) ?? job.accountId}
          </span>
        </button>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      width: '130px',
      render: (job) => <JobStatusDot status={job.status} />,
    },
    {
      key: 'progress',
      header: 'Progress',
      width: '200px',
      secondary: true,
      render: (job) => {
        const live = progress[job.id];
        const value = live?.progress ?? job.progress;
        if (job.status !== 'running') {
          return <span className="tabular text-muted-foreground">{Math.round(value)}%</span>;
        }
        return (
          <div className="grid gap-1">
            <Progress value={value} className="h-1.5" />
            <span className="truncate text-xs text-muted-foreground">
              {live?.step ?? 'Working'}
            </span>
          </div>
        );
      },
    },
    {
      key: 'attempts',
      header: 'Attempt',
      width: '90px',
      secondary: true,
      render: (job) => (
        <span className="tabular text-muted-foreground">
          {job.retryCount + 1} of {job.maxRetries + 1}
        </span>
      ),
    },
    {
      key: 'created',
      header: 'Created',
      width: '140px',
      secondary: true,
      render: (job) => <span className="text-muted-foreground">{relativeTime(job.createdAt)}</span>,
    },
    {
      key: 'actions',
      header: '',
      align: 'right',
      width: '210px',
      render: (job) => (
        <div className="flex justify-end gap-1.5">
          {!TERMINAL.includes(job.status) && (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => cancel.mutate(job.id, { onError: fail })}
              disabled={cancel.isPending && cancel.variables === job.id}
            >
              <XCircle /> Cancel
            </Button>
          )}
          {(job.status === 'failed' || job.status === 'cancelled') && (
            <Button
              size="sm"
              variant="outline"
              onClick={() =>
                retry.mutate(job.id, {
                  onError: fail,
                  onSuccess: () => toast.success('Queued again'),
                })
              }
              disabled={retry.isPending && retry.variables === job.id}
            >
              <RotateCcw /> Retry
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={() => setInspecting(job)}>
            Details
          </Button>
        </div>
      ),
    },
  ];

  return (
    <div className="grid gap-6">
      <PageHeader
        title="Queue"
        description="Work is stored before it runs, so nothing here is lost on a restart."
        actions={
          <Button
            variant="outline"
            disabled={cancelAll.isPending || activeCount === 0}
            onClick={() =>
              cancelAll.mutate(undefined, {
                onError: fail,
                onSuccess: (result) =>
                  toast.success(
                    `Cancelled ${result.cancelled} job${result.cancelled === 1 ? '' : 's'}`,
                  ),
              })
            }
          >
            <OctagonX /> Stop everything
          </Button>
        }
      />

      {stats.isSuccess && (
        <div className="grid grid-cols-4 divide-x rounded-lg border bg-card sm:grid-cols-7">
          {JOB_STATUSES.map((status) => (
            <button
              key={status}
              type="button"
              onClick={() => setFilter(status)}
              aria-pressed={filter === status}
              className={cn(
                'grid gap-0.5 px-4 py-3 text-left transition-colors hover:bg-accent/60',
                filter === status && 'bg-accent',
              )}
            >
              <span className="tabular text-lg font-semibold">{stats.data[status]}</span>
              <span className="text-xs text-muted-foreground">{status}</span>
            </button>
          ))}
        </div>
      )}

      <Tabs value={filter} onValueChange={setFilter}>
        <TabsList>
          <TabsTrigger value="active">Active</TabsTrigger>
          <TabsTrigger value="finished">Finished</TabsTrigger>
          {(JOB_STATUSES as readonly string[]).includes(filter) && (
            <TabsTrigger value={filter}>{humanise(filter)}</TabsTrigger>
          )}
        </TabsList>
      </Tabs>

      {jobs.isError && <ErrorNotice error={jobs.error} />}

      <DataTable
        columns={columns}
        rows={jobs.data?.items ?? []}
        rowKey={(job) => job.id}
        loading={jobs.isFetching}
        empty={
          <EmptyState
            title="No jobs here"
            description="Compose work for one or more accounts and it appears in this list."
          />
        }
      />

      <JobDetails job={inspecting} onClose={() => setInspecting(null)} />
    </div>
  );
};

const JobDetails = ({ job, onClose }: { job: Job | null; onClose: () => void }): ReactElement => (
  <Modal
    open={job !== null}
    title={job === null ? '' : humanise(job.type)}
    {...(job === null ? {} : { description: `Job ${job.id}` })}
    onClose={onClose}
    size="wide"
  >
    {job !== null && (
      <>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-4">
          <Detail label="Status">
            <JobStatusDot status={job.status} />
          </Detail>
          <Detail label="Account">
            <span className="font-mono text-xs">{job.accountId}</span>
          </Detail>
          <Detail label="Priority">{job.priority}</Detail>
          <Detail label="Attempt">{`${job.retryCount + 1} of ${job.maxRetries + 1}`}</Detail>
          <Detail label="Created">{dateTime(job.createdAt)}</Detail>
          <Detail label="Started">{dateTime(job.startedAt)}</Detail>
          <Detail label="Finished">{dateTime(job.finishedAt)}</Detail>
          <Detail label="Next attempt">{dateTime(job.runAfter)}</Detail>
        </dl>

        {job.lastError !== null && (
          <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm">
            <p className="font-mono text-xs text-destructive">{job.lastError.code}</p>
            <p className="mt-1">{job.lastError.message}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {job.lastError.retryable
                ? 'Retrying can succeed.'
                : 'Retrying will not help until the cause is fixed.'}
            </p>
          </div>
        )}

        {job.result !== null && <Payload label="Result" value={job.result} />}
        <Payload label="Payload" value={job.payload} />
      </>
    )}
  </Modal>
);

const Detail = ({ label, children }: { label: string; children: ReactNode }): ReactElement => (
  <div className="grid gap-0.5">
    <dt className="text-xs text-muted-foreground">{label}</dt>
    <dd>{children}</dd>
  </div>
);

const Payload = ({ label, value }: { label: string; value: unknown }): ReactElement => (
  <div className="grid gap-1.5">
    <p className="text-xs text-muted-foreground">{label}</p>
    <pre className="max-h-56 overflow-auto rounded-md border bg-muted/40 p-3 font-mono text-xs leading-relaxed">
      {JSON.stringify(value, null, 2)}
    </pre>
  </div>
);
