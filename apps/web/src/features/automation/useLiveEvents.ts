import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { ServerEventSchema, WEBSOCKET_PATH, type ServerEvent } from '@fb/shared';
import { WEB_CONFIG } from '../../lib/env';
import { useLiveStore } from './liveStore';

const RECONNECT_BASE_MS = 1_000;
const RECONNECT_MAX_MS = 15_000;

const socketUrl = (): string => {
  const base = WEB_CONFIG.apiBaseUrl === '' ? window.location.origin : WEB_CONFIG.apiBaseUrl;
  const url = new URL(WEBSOCKET_PATH, base);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
};

/**
 * One socket for the whole application.
 *
 * An event never carries the new state into a component directly: it
 * invalidates the queries it affects and lets TanStack Query refetch. That way
 * a missed frame during a reconnect costs a refetch, not a wrong screen.
 */
export const useLiveEvents = (): void => {
  const queryClient = useQueryClient();
  const setConnection = useLiveStore((state) => state.setConnection);
  const record = useLiveStore((state) => state.record);

  // Held in a ref so a re-render never tears down a healthy socket.
  const socketRef = useRef<WebSocket | null>(null);
  const attemptRef = useRef(0);
  const closedByUs = useRef(false);

  useEffect(() => {
    closedByUs.current = false;
    let reconnectTimer: number | null = null;

    const connect = (): void => {
      reconnectTimer = null;
      const socket = new WebSocket(socketUrl());
      socketRef.current = socket;
      setConnection('connecting');

      socket.onopen = () => {
        attemptRef.current = 0;
        setConnection('open');
      };

      socket.onmessage = (message: MessageEvent<string>) => {
        const parsed = ServerEventSchema.safeParse(safeParse(message.data));
        if (!parsed.success) return;

        record(parsed.data);
        invalidate(queryClient, parsed.data);
      };

      socket.onclose = () => {
        setConnection('closed');
        if (closedByUs.current) return;

        // Backing off keeps a restarting server from being hammered by every
        // open tab at once.
        attemptRef.current += 1;
        const delay = Math.min(RECONNECT_MAX_MS, RECONNECT_BASE_MS * 2 ** (attemptRef.current - 1));
        reconnectTimer = window.setTimeout(connect, delay);
      };

      socket.onerror = () => socket.close();
    };

    connect();

    return () => {
      closedByUs.current = true;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);

      const socket = socketRef.current;
      socketRef.current = null;
      if (socket === null) return;

      // Closing a socket that is still connecting logs a browser warning; let
      // it finish opening and close it then. StrictMode mounts twice in
      // development, which is exactly this case.
      if (socket.readyState === WebSocket.CONNECTING) {
        socket.onopen = () => socket.close();
        socket.onmessage = null;
      } else {
        socket.close();
      }
    };
  }, [queryClient, record, setConnection]);
};

const safeParse = (raw: string): unknown => {
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
};

/** Maps an event to the queries it makes stale. */
const invalidate = (queryClient: ReturnType<typeof useQueryClient>, event: ServerEvent): void => {
  const refresh = (key: string): void => {
    void queryClient.invalidateQueries({ queryKey: [key] });
  };

  switch (event.type) {
    case 'account.created':
    case 'account.updated':
    case 'account.deleted':
    case 'account.status.changed':
    case 'browser.started':
    case 'browser.stopped':
    case 'browser.error':
      refresh('accounts');
      refresh('sessions');
      refresh('dashboard');
      break;

    case 'job.created':
    case 'job.started':
    case 'job.completed':
    case 'job.failed':
    case 'job.cancelled':
    case 'job.retrying':
      refresh('jobs');
      refresh('queue-stats');
      refresh('dashboard');
      break;

    case 'log.created':
      refresh('logs');
      break;

    case 'groups.changed':
      refresh('groups');
      break;

    case 'input.requested':
    case 'input.resolved':
      refresh('operator-requests');
      break;

    // Progress and statistics are read from the live store, so they need no
    // refetch at all.
    case 'job.progress':
    case 'queue.stats':
    case 'connection.ready':
      break;
  }
};
