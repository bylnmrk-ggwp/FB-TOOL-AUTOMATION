import { useMemo, useState, type ReactElement } from 'react';
import type { Job, JobStatus } from '@fb/shared';
import { JOB_STATUSES } from '@fb/shared';
import { JobStatusBadge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { EmptyState, ErrorNotice } from '../../components/ui/Feedback';
import { PageHeader } from '../../components/ui/PageHeader';
import { Modal } from '../../components/dialogs/Modal';
import { DataTable, type Column } from '../../components/tables/DataTable';
import { useAccounts } from '../../features/accounts/hooks';
import { useCancelJob, useJobs, useQueueStats, useRetryJob } from '../../features/queue/hooks';
import { useLiveStore } from '../../features/automation/liveStore';
import { dateTime, humanise, relativeTime } from '../../lib/format';
import './QueuePage.css';

const ACTIVE: readonly JobStatus[] = ['pending', 'queued', 'running', 'retrying'];
const TERMINAL: readonly JobStatus[] = ['completed', 'failed', 'cancelled'];

type Filter = 'active' | 'finished' | JobStatus;

const FILTERS: ReadonlyArray<{ value: Filter; label: string }> = [
  { value: 'active', label: 'Active' },
  { value: 'finished', label: 'Finished' },
  ...JOB_STATUSES.map((status) => ({ value: status, label: humanise(status) })),
];

const statusesFor = (filter: Filter): readonly JobStatus[] => {
  if (filter === 'active') return ACTIVE;
  if (filter === 'finished') return TERMINAL;
  return [filter];
};

export const QueuePage = (): ReactElement => {
  const [filter, setFilter] = useState<Filter>('active');
  const [inspecting, setInspecting] = useState<Job | null>(null);

  const jobs = useJobs(useMemo(() => ({ status: [...statusesFor(filter)], limit: 100 }), [filter]));
  const stats = useQueueStats();
  const accounts = useAccounts({ limit: 200 });
  const cancel = useCancelJob();
  const retry = useRetryJob();
  const progress = useLiveStore((state) => state.progress);

  const accountName = useMemo(() => {
    const names = new Map<string, string>();
    for (const account of accounts.data?.items ?? []) names.set(account.id, account.displayName);
    return names;
  }, [accounts.data]);

  const columns: ReadonlyArray<Column<Job>> = [
    {
      key: 'type',
      header: 'Action',
      render: (job) => (
        <div className="queue__action">
          <span>{humanise(job.type)}</span>
          <span className="queue__secondary">
            {accountName.get(job.accountId) ?? job.accountId}
          </span>
        </div>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      width: '120px',
      render: (job) => <JobStatusBadge status={job.status} />,
    },
    {
      key: 'progress',
      header: 'Progress',
      width: '180px',
      render: (job) => {
        const live = progress[job.id];
        const value = live?.progress ?? job.progress;
        if (job.status !== 'running') return `${Math.round(value)}%`;

        return (
          <div className="queue__progress" title={live?.step ?? ''}>
            <div className="queue__progress-bar" style={{ width: `${value}%` }} />
            <span className="queue__progress-label">{live?.step ?? `${Math.round(value)}%`}</span>
          </div>
        );
      },
    },
    {
      key: 'attempts',
      header: 'Attempts',
      width: '100px',
      render: (job) => `${job.retryCount + 1} / ${job.maxRetries + 1}`,
    },
    {
      key: 'created',
      header: 'Created',
      width: '140px',
      render: (job) => relativeTime(job.createdAt),
    },
    {
      key: 'actions',
      header: 'Actions',
      align: 'right',
      width: '250px',
      render: (job) => (
        <div className="queue__actions">
          <Button size="sm" variant="ghost" onClick={() => setInspecting(job)}>
            Inspect
          </Button>

          {!TERMINAL.includes(job.status) && (
            <Button
              size="sm"
              onClick={() => cancel.mutate(job.id)}
              loading={cancel.isPending && cancel.variables === job.id}
            >
              Cancel
            </Button>
          )}

          {(job.status === 'failed' || job.status === 'cancelled') && (
            <Button
              size="sm"
              variant="primary"
              onClick={() => retry.mutate(job.id)}
              loading={retry.isPending && retry.variables === job.id}
            >
              Retry
            </Button>
          )}
        </div>
      ),
    },
  ];

  return (
    <div className="page">
      <PageHeader
        title="Queue"
        description="Jobs are stored before they run, so nothing here is lost on a restart."
      />

      {stats.isSuccess && (
        <div className="queue__stats">
          {JOB_STATUSES.map((status) => (
            <button
              key={status}
              type="button"
              className={`queue__stat${filter === status ? ' queue__stat--active' : ''}`}
              onClick={() => setFilter(status)}
            >
              <span className="queue__stat-value">{stats.data[status]}</span>
              <span className="queue__stat-label">{status}</span>
            </button>
          ))}
        </div>
      )}

      <div className="queue__filters" role="tablist" aria-label="Job filter">
        {FILTERS.map((option) => (
          <button
            key={option.value}
            type="button"
            role="tab"
            aria-selected={filter === option.value}
            className={`queue__filter${filter === option.value ? ' queue__filter--active' : ''}`}
            onClick={() => setFilter(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>

      {jobs.isError && <ErrorNotice error={jobs.error} />}
      {cancel.error !== null && <ErrorNotice error={cancel.error} />}
      {retry.error !== null && <ErrorNotice error={retry.error} />}

      <DataTable
        columns={columns}
        rows={jobs.data?.items ?? []}
        rowKey={(job) => job.id}
        loading={jobs.isFetching}
        empty={
          <EmptyState
            title="Nothing here"
            description="Create work from the Compose page and it will appear here."
          />
        }
      />

      <JobDetails job={inspecting} onClose={() => setInspecting(null)} />
    </div>
  );
};

const JobDetails = ({ job, onClose }: { job: Job | null; onClose: () => void }): ReactElement => (
  <Modal open={job !== null} title={job === null ? '' : `${humanise(job.type)}`} onClose={onClose}>
    {job !== null && (
      <>
        <dl className="queue__details">
          <Detail label="Job" value={job.id} mono />
          <Detail label="Account" value={job.accountId} mono />
          <Detail label="Status" value={job.status} />
          <Detail label="Priority" value={String(job.priority)} />
          <Detail label="Created" value={dateTime(job.createdAt)} />
          <Detail label="Started" value={dateTime(job.startedAt)} />
          <Detail label="Finished" value={dateTime(job.finishedAt)} />
          <Detail label="Next attempt" value={dateTime(job.runAfter)} />
        </dl>

        {job.lastError !== null && (
          <div className="queue__error">
            <p className="queue__error-code">{job.lastError.code}</p>
            <p>{job.lastError.message}</p>
            <p className="muted">
              {job.lastError.retryable ? 'This error can be retried.' : 'Retrying will not help.'}
            </p>
          </div>
        )}

        {job.result !== null && (
          <div>
            <p className="field__label">Result</p>
            <pre className="queue__payload">{JSON.stringify(job.result, null, 2)}</pre>
          </div>
        )}

        <div>
          <p className="field__label">Payload</p>
          <pre className="queue__payload">{JSON.stringify(job.payload, null, 2)}</pre>
        </div>
      </>
    )}
  </Modal>
);

const Detail = ({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}): ReactElement => (
  <div>
    <dt>{label}</dt>
    <dd className={mono ? 'mono' : undefined}>{value}</dd>
  </div>
);
