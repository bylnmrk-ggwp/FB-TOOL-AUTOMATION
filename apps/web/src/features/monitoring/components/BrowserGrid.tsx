import { useEffect, useRef, useState, type ReactElement } from 'react';
import { unpackTerminalFrame, type BrowserSessionView } from '@fb/shared';
import { AccountStatusDot } from '@/components/common/StatusDot';
import { authHeaders } from '@/lib/auth';
import { WEB_CONFIG } from '@/lib/env';
import { relativeTime } from '../../../lib/format';

/** How often each tile pulls a fresh frame. Slow enough for 5+ at once. */
const REFRESH_MS = 2_500;

/**
 * One tile: an account's browser drawn the way a terminal browser would draw
 * it, in the 256 colours of an xterm, refreshed on its own timer.
 *
 * The server sends one byte per pixel, so a frame is a few kilobytes where a
 * JPEG thumbnail was tens of them. A 404 (the session just ended) leaves the
 * last good frame on screen, and the request carries its token in a header,
 * never in the URL.
 */
const BrowserTile = ({
  session,
  name,
}: {
  session: BrowserSessionView;
  name: string;
}): ReactElement => {
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const [size, setSize] = useState<{ width: number; height: number } | null>(null);

  useEffect(() => {
    let active = true;
    const url = `${WEB_CONFIG.apiBaseUrl}/api/v1/accounts/${session.accountId}/browser/terminal`;

    const draw = async (): Promise<void> => {
      try {
        // `no-store` keeps the frame fresh, and a stable URL lets a
        // cross-origin panel reuse its cached preflight.
        const response = await fetch(url, { cache: 'no-store', headers: authHeaders() });
        if (!active || !response.ok) return;
        const frame = unpackTerminalFrame(new Uint8Array(await response.arrayBuffer()));
        const target = canvas.current;
        if (!active || frame === null || target === null) return;

        if (target.width !== frame.width) target.width = frame.width;
        if (target.height !== frame.height) target.height = frame.height;
        const image = new ImageData(frame.width, frame.height);
        image.data.set(frame.rgba);
        target.getContext('2d')?.putImageData(image, 0, 0);
        setSize((current) =>
          current?.width === frame.width && current.height === frame.height
            ? current
            : { width: frame.width, height: frame.height },
        );
      } catch {
        // A missed frame is fine; the next tick tries again.
      }
    };

    void draw();
    const timer = setInterval(() => void draw(), REFRESH_MS);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [session.accountId]);

  return (
    <figure className="grid overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950 font-mono text-zinc-300">
      <div className="flex items-center gap-1.5 border-b border-zinc-800 px-2 py-1 text-[11px]">
        <span aria-hidden="true" className="text-emerald-400">
          $
        </span>
        <span className="min-w-0 truncate">{name}</span>
        <span className="ml-auto shrink-0 text-zinc-600">
          {size === null ? '' : `${size.width}×${Math.ceil(size.height / 2)}`}
        </span>
        <span className="shrink-0">
          <AccountStatusDot status={session.status} />
        </span>
      </div>
      {/* The canvas is taken out of flow: left in, its own pixel size would
          stretch the box past the 16:10 the grid is laid out for. */}
      <div className="relative aspect-[16/10] overflow-hidden bg-black">
        <canvas
          ref={canvas}
          role="img"
          aria-label={`${name}'s browser, drawn as a terminal screen`}
          className={
            size === null
              ? 'hidden'
              : 'absolute inset-0 h-full w-full object-cover object-top [image-rendering:pixelated]'
          }
        />
        {size === null && (
          <div className="grid h-full place-items-center text-[11px] text-zinc-500">
            <span>
              waiting for the first frame<span className="animate-pulse">▌</span>
            </span>
          </div>
        )}
      </div>
      <figcaption className="truncate border-t border-zinc-800 px-2 py-1 text-[11px] text-zinc-500">
        {session.currentUrl ?? `started ${relativeTime(session.startedAt)}`}
      </figcaption>
    </figure>
  );
};

/**
 * Every open browser as a live grid of terminal screens, five to a row. Built for watching a
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
