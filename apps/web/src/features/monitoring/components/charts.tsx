import { useId, useState, type ReactElement } from 'react';
import type { HourlyJobs, LoginStatus } from '@fb/shared';
import { Button } from '@/components/ui/button';
import { LOGIN_LABELS } from '@/components/common/StatusDot';
import { cn } from '@/lib/utils';
import { humanise } from '../../../lib/format';

/**
 * Hand-drawn SVG, no chart library. Three charts, one visual system: thin
 * marks, 2px surface gaps, hairline grid, text in text tokens never in the
 * series colour, a legend for anything with two or more series, a hover
 * tooltip, and a table view for every one of them.
 *
 * Colour carries meaning here and nowhere else on the page: the outcome of a
 * job (status palette) and the state of an account (status palette). The
 * one categorical chart has one series and so one colour.
 */

const STATUS_FILL = {
  completed: 'var(--success)',
  failed: 'var(--destructive)',
  cancelled: 'var(--muted-foreground)',
} as const;

const LOGIN_FILL: Record<LoginStatus, string> = {
  logged_in: 'var(--success)',
  unknown: 'var(--muted-foreground)',
  logged_out: 'var(--warning)',
  restricted: 'var(--warning)',
  checkpoint: 'var(--destructive)',
  two_factor: 'var(--destructive)',
  email_confirmation: 'var(--destructive)',
  captcha: 'var(--destructive)',
  disabled: 'var(--destructive)',
};

const Legend = ({ items }: { items: Array<{ label: string; fill: string }> }): ReactElement => (
  <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
    {items.map((item) => (
      <li key={item.label} className="flex items-center gap-1.5">
        <span
          className="inline-block size-2.5 rounded-sm"
          style={{ background: item.fill }}
          aria-hidden="true"
        />
        {item.label}
      </li>
    ))}
  </ul>
);

const TableToggle = ({ open, onToggle }: { open: boolean; onToggle: () => void }): ReactElement => (
  <Button type="button" variant="ghost" size="xs" onClick={onToggle} aria-pressed={open}>
    {open ? 'Show chart' : 'Show table'}
  </Button>
);

const hourLabel = (iso: string): string => {
  const date = new Date(iso);
  return `${String(date.getHours()).padStart(2, '0')}:00`;
};

// --- Jobs finished per hour, stacked by outcome -----------------------------

export const HourlyJobsChart = ({ data }: { data: HourlyJobs[] }): ReactElement => {
  const [table, setTable] = useState(false);
  const [hover, setHover] = useState<number | null>(null);
  const titleId = useId();

  const width = 720;
  const height = 200;
  const pad = { top: 12, right: 8, bottom: 26, left: 32 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const max = Math.max(
    1,
    ...data.map((bucket) => bucket.completed + bucket.failed + bucket.cancelled),
  );
  const ticks = niceTicks(max);
  const slot = innerW / Math.max(1, data.length);
  const barW = Math.min(24, slot * 0.6);
  const gap = 2;
  const total = data.reduce(
    (sum, bucket) => sum + bucket.completed + bucket.failed + bucket.cancelled,
    0,
  );

  const y = (value: number): number =>
    pad.top + innerH - (value / (ticks[ticks.length - 1] ?? max)) * innerH;

  return (
    <figure className="grid gap-3" aria-labelledby={titleId}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <figcaption id={titleId} className="text-sm font-medium text-muted-foreground">
          Jobs finished, last 24 hours
          <span className="ml-2 text-foreground">{total}</span>
        </figcaption>
        <TableToggle open={table} onToggle={() => setTable((value) => !value)} />
      </div>

      {table ? (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full text-sm">
            <thead className="text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Hour</th>
                <th className="px-3 py-2 text-right font-medium">Completed</th>
                <th className="px-3 py-2 text-right font-medium">Failed</th>
                <th className="px-3 py-2 text-right font-medium">Cancelled</th>
              </tr>
            </thead>
            <tbody>
              {data.map((bucket) => (
                <tr key={bucket.hour} className="border-t">
                  <td className="px-3 py-1.5">{hourLabel(bucket.hour)}</td>
                  <td className="px-3 py-1.5 text-right">{bucket.completed}</td>
                  <td className="px-3 py-1.5 text-right">{bucket.failed}</td>
                  <td className="px-3 py-1.5 text-right">{bucket.cancelled}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="relative">
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="h-auto w-full"
            role="img"
            aria-label="Jobs finished per hour, by outcome"
          >
            {ticks.map((tick) => (
              <g key={tick}>
                <line
                  x1={pad.left}
                  x2={width - pad.right}
                  y1={y(tick)}
                  y2={y(tick)}
                  stroke="var(--border)"
                  strokeWidth={1}
                />
                <text
                  x={pad.left - 6}
                  y={y(tick) + 3}
                  textAnchor="end"
                  fontSize={10}
                  fill="var(--muted-foreground)"
                >
                  {tick}
                </text>
              </g>
            ))}

            {data.map((bucket, index) => {
              const x = pad.left + index * slot + (slot - barW) / 2;
              const segments = [
                { key: 'completed', value: bucket.completed, fill: STATUS_FILL.completed },
                { key: 'failed', value: bucket.failed, fill: STATUS_FILL.failed },
                { key: 'cancelled', value: bucket.cancelled, fill: STATUS_FILL.cancelled },
              ].filter((segment) => segment.value > 0);
              let stack = 0;
              const isHover = hover === index;

              return (
                <g
                  key={bucket.hour}
                  onMouseEnter={() => setHover(index)}
                  onMouseLeave={() => setHover(null)}
                >
                  {/* Hit target wider than the mark. */}
                  <rect
                    x={pad.left + index * slot}
                    y={pad.top}
                    width={slot}
                    height={innerH}
                    fill="transparent"
                  />
                  {segments.map((segment, segmentIndex) => {
                    const top = y(stack + segment.value);
                    const bottom = y(stack) - (segmentIndex === 0 ? 0 : gap);
                    stack += segment.value;
                    const h = Math.max(0, bottom - top);
                    const isTop = segmentIndex === segments.length - 1;
                    return (
                      <rect
                        key={segment.key}
                        x={x}
                        y={top}
                        width={barW}
                        height={h}
                        rx={isTop ? 4 : 0}
                        fill={segment.fill}
                        opacity={hover === null || isHover ? 1 : 0.45}
                      />
                    );
                  })}
                  {index % 4 === 0 && (
                    <text
                      x={pad.left + index * slot + slot / 2}
                      y={height - 8}
                      textAnchor="middle"
                      fontSize={10}
                      fill="var(--muted-foreground)"
                    >
                      {hourLabel(bucket.hour)}
                    </text>
                  )}
                </g>
              );
            })}
          </svg>

          {hover !== null && data[hover] !== undefined && (
            <div
              className={cn(
                'pointer-events-none absolute top-0 rounded-md border bg-popover px-2.5 py-1.5 text-xs shadow-md',
              )}
              style={{
                left: `${((pad.left + hover * slot + slot / 2) / width) * 100}%`,
                transform: 'translateX(-50%)',
              }}
            >
              <div className="font-medium">{hourLabel(data[hover].hour)}</div>
              <div className="text-muted-foreground">
                {data[hover].completed} completed, {data[hover].failed} failed,{' '}
                {data[hover].cancelled} cancelled
              </div>
            </div>
          )}
        </div>
      )}

      <Legend
        items={[
          { label: 'Completed', fill: STATUS_FILL.completed },
          { label: 'Failed', fill: STATUS_FILL.failed },
          { label: 'Cancelled', fill: STATUS_FILL.cancelled },
        ]}
      />
    </figure>
  );
};

// --- Roster health: one stacked bar of login states -------------------------

const LOGIN_ORDER: LoginStatus[] = [
  'logged_in',
  'unknown',
  'logged_out',
  'restricted',
  'captcha',
  'two_factor',
  'checkpoint',
  'email_confirmation',
  'disabled',
];

export const RosterHealthBar = ({
  counts,
}: {
  counts: Partial<Record<LoginStatus, number>>;
}): ReactElement => {
  const [table, setTable] = useState(false);
  const titleId = useId();
  const total = LOGIN_ORDER.reduce((sum, status) => sum + (counts[status] ?? 0), 0);
  const present = LOGIN_ORDER.filter((status) => (counts[status] ?? 0) > 0);

  return (
    <figure className="grid gap-3" aria-labelledby={titleId}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <figcaption id={titleId} className="text-sm font-medium text-muted-foreground">
          Roster by login state
          <span className="ml-2 text-foreground">{total}</span>
        </figcaption>
        <TableToggle open={table} onToggle={() => setTable((value) => !value)} />
      </div>

      {total === 0 ? (
        <p className="text-sm text-muted-foreground">No accounts yet.</p>
      ) : table ? (
        <table className="w-full text-sm">
          <tbody>
            {present.map((status) => (
              <tr key={status} className="border-t">
                <td className="py-1.5">{LOGIN_LABELS[status]}</td>
                <td className="py-1.5 text-right tabular">{counts[status] ?? 0}</td>
                <td className="py-1.5 text-right text-muted-foreground tabular">
                  {Math.round((100 * (counts[status] ?? 0)) / total)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <>
          <div
            className="flex h-4 w-full gap-0.5 overflow-hidden rounded-md"
            role="img"
            aria-label="Accounts by login state"
          >
            {present.map((status) => (
              <div
                key={status}
                title={`${LOGIN_LABELS[status]}: ${counts[status] ?? 0}`}
                style={{
                  width: `${(100 * (counts[status] ?? 0)) / total}%`,
                  background: LOGIN_FILL[status],
                }}
              />
            ))}
          </div>
          <Legend
            items={present.map((status) => ({
              label: `${LOGIN_LABELS[status]} ${counts[status] ?? 0}`,
              fill: LOGIN_FILL[status],
            }))}
          />
        </>
      )}
    </figure>
  );
};

// --- Finished jobs by type: single series, horizontal bars ------------------

export const JobsByTypeChart = ({
  data,
}: {
  data: Array<{ type: string; count: number }>;
}): ReactElement => {
  const [table, setTable] = useState(false);
  const titleId = useId();
  const max = Math.max(1, ...data.map((row) => row.count));
  const rows = data.slice(0, 8);

  return (
    <figure className="grid gap-3" aria-labelledby={titleId}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <figcaption id={titleId} className="text-sm font-medium text-muted-foreground">
          Finished by type, last 24 hours
        </figcaption>
        {rows.length > 0 && (
          <TableToggle open={table} onToggle={() => setTable((value) => !value)} />
        )}
      </div>

      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nothing finished yet.</p>
      ) : table ? (
        <table className="w-full text-sm">
          <tbody>
            {rows.map((row) => (
              <tr key={row.type} className="border-t">
                <td className="py-1.5">{humanise(row.type)}</td>
                <td className="py-1.5 text-right tabular">{row.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <ul className="grid gap-2" role="img" aria-label="Finished jobs by type">
          {rows.map((row) => (
            <li
              key={row.type}
              className="grid grid-cols-[140px_1fr_40px] items-center gap-3 text-sm"
              title={`${humanise(row.type)}: ${row.count}`}
            >
              <span className="truncate text-muted-foreground">{humanise(row.type)}</span>
              <div
                className="h-3 rounded-r-sm"
                style={{ width: `${(100 * row.count) / max}%`, background: 'var(--chart-1)' }}
              />
              <span className="text-right tabular">{row.count}</span>
            </li>
          ))}
        </ul>
      )}
    </figure>
  );
};

/** Round tick values: 0 / 5 / 10, never 0 / 3.7 / 7.4. */
const niceTicks = (max: number): number[] => {
  // Counts, so a step is never smaller than one job.
  const raw = Math.max(1, max / 4);
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = Math.max(
    1,
    [1, 2, 5, 10].map((m) => m * magnitude).find((candidate) => candidate >= raw) ?? magnitude,
  );
  const top = Math.ceil(max / step) * step;
  const ticks = [];
  for (let value = 0; value <= top; value += step) ticks.push(value);
  return ticks;
};
