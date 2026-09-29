import { useEffect, useRef, useState, type ReactElement } from 'react';
import type { BrowserSessionView } from '@fb/shared';
import { AccountStatusDot } from '@/components/common/StatusDot';
import { WEB_CONFIG } from '@/lib/env';
import { relativeTime } from '../../../lib/format';

/** How often each tile pulls a fresh JPEG. Slow enough for 5+ at once. */
const REFRESH_MS = 2_500;

/**
 * One tile: a live thumbnail of an account's browser, refreshed on its own
 * timer. The image is fetched as a blob so a 404 (the session just ended)
 * leaves the last good frame instead of a broken-image icon, and so the URL
 * carries no auth in a query string.
 */
const BrowserTile = ({
  session,
  name,
}: {
  session: BrowserSessionView;
  name: string;
}): ReactElement => {
  const [src, setSrc] = useState<string | null>(null);
  const objectUrl = useRef<string | null>(null);

  useEffect(() => {
    let active = true;
    const url = `${WEB_CONFIG.apiBaseUrl}/api/v1/accounts/${session.accountId}/browser/screenshot`;

    const shoot = async (): Promise<void> => {
      try {
        const response = await fetch(`${url}?t=${Date.now()}`, { cache: 'no-store' });
        if (!active || !response.ok) return;
        const blob = await response.blob();
        if (!active) return;
        if (objectUrl.current !== null) URL.revokeObjectURL(objectUrl.current);
        objectUrl.current = URL.createObjectURL(blob);
        setSrc(objectUrl.current);
      } catch {
        // A missed frame is fine; the next tick tries again.
      }
    };

    void shoot();
    const timer = setInterval(() => void shoot(), REFRESH_MS);
    return () => {
      active = false;
      clearInterval(timer);
      if (objectUrl.current !== null) URL.revokeObjectURL(objectUrl.current);
      objectUrl.current = null;
    };
  }, [session.accountId]);

  return (
    <figure className="grid gap-1.5 overflow-hidden rounded-lg border bg-card">
      <div className="relative aspect-[16/10] overflow-hidden bg-muted">
        {src === null ? (
          <div className="grid h-full place-items-center text-xs text-muted-foreground">
            Waiting for the first frame…
          </div>
        ) : (
          <img
            src={src}
            alt={`${name}'s browser`}
            className="h-full w-full object-cover object-top"
          />
        )}
        <span className="absolute right-1.5 top-1.5">
          <AccountStatusDot status={session.status} />
        </span>
      </div>
      <figcaption className="grid gap-0.5 px-2.5 pb-2">
        <span className="truncate text-sm font-medium">{name}</span>
        <span className="truncate text-xs text-muted-foreground">
          {session.currentUrl ?? `started ${relativeTime(session.startedAt)}`}
        </span>
      </figcaption>
    </figure>
  );
};

/**
 * Every open browser as a live grid, five to a row. Built for watching a
 * headless batch: the windows are invisible on the machine, so this is the
 * only way to see what each account's page is doing.
 */
export const BrowserGrid = ({
  sessions,
  accountName,
}: {
  sessions: readonly BrowserSessionView[];
  accountName: (id: string) => string;
}): ReactElement => (
  <div className="grid grid-cols-2 gap-3 p-4 sm:grid-cols-3 lg:grid-cols-5">
    {sessions.map((session) => (
      <BrowserTile
        key={session.sessionId}
        session={session}
        name={accountName(session.accountId)}
      />
    ))}
  </div>
);
