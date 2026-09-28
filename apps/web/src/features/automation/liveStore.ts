import { create } from 'zustand';
import type { QueueStats, ServerEvent } from '@fb/shared';

export type ConnectionState = 'connecting' | 'open' | 'closed';

export interface JobProgress {
  jobId: string;
  accountId: string;
  progress: number;
  step: string;
  at: string;
}

interface LiveState {
  connection: ConnectionState;
  /** Newest first, capped: this is a live feed, not a log store. */
  recent: ServerEvent[];
  progress: Record<string, JobProgress>;
  queueStats: QueueStats | null;
  setConnection: (state: ConnectionState) => void;
  record: (event: ServerEvent) => void;
  clear: () => void;
}

const MAX_RECENT = 200;

/**
 * The only client state that genuinely belongs in a store: it arrives by push,
 * it is shared by several pages, and it has no server endpoint to refetch from.
 * Everything the server owns stays in TanStack Query.
 */
export const useLiveStore = create<LiveState>()((set) => ({
  connection: 'connecting',
  recent: [],
  progress: {},
  queueStats: null,

  setConnection: (connection) => set({ connection }),

  record: (event) =>
    set((state) => {
      const recent = [event, ...state.recent].slice(0, MAX_RECENT);

      if (event.type === 'job.progress') {
        return {
          recent,
          progress: {
            ...state.progress,
            [event.payload.jobId]: {
              jobId: event.payload.jobId,
              accountId: event.payload.accountId,
              progress: event.payload.progress,
              step: event.payload.step,
              at: event.timestamp,
            },
          },
        };
      }

      if (event.type === 'queue.stats') return { recent, queueStats: event.payload };

      // A finished job stops having progress; leaving it would show a stale bar.
      if (
        event.type === 'job.completed' ||
        event.type === 'job.failed' ||
        event.type === 'job.cancelled'
      ) {
        const progress = { ...state.progress };
        delete progress[event.payload.id];
        return { recent, progress };
      }

      return { recent };
    }),

  clear: () => set({ recent: [], progress: {} }),
}));
