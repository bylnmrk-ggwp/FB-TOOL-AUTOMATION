import {
  createId,
  nowIso,
  OperatorInputCancelledError,
  OperatorInputTimeoutError,
  OperatorRequestNotFoundError,
  type InputKind,
  type OperatorAnswer,
  type OperatorRequest,
} from '@fb/shared';
import type { EventPublisher } from '../ports/EventPublisher.js';
import type { Logger } from '../ports/Logger.js';

interface Pending {
  request: OperatorRequest;
  resolve: (answer: OperatorAnswer) => void;
  reject: (error: Error) => void;
  timer: ReturnType<typeof setTimeout>;
}

export interface AskOptions {
  jobId: string;
  accountId: string;
  kind: InputKind;
  message: string;
  expectsText?: boolean;
  timeoutMs: number;
  /** Aborting the job answers the request as cancelled. */
  signal?: AbortSignal;
}

/**
 * The human-in-the-loop seam. A job that meets a captcha, a code prompt or a
 * checkpoint stops here and waits; every open browser tab is told; the first
 * person to answer settles it for all of them.
 *
 * Requests live in memory only: a request that a restart loses belonged to a
 * job the restart failed anyway.
 */
export class OperatorInputService {
  private readonly pending = new Map<string, Pending>();

  constructor(
    private readonly events: EventPublisher,
    private readonly logger: Logger,
  ) {}

  ask(options: AskOptions): Promise<OperatorAnswer> {
    const now = new Date();
    const request: OperatorRequest = {
      id: createId('ask'),
      jobId: options.jobId,
      accountId: options.accountId,
      kind: options.kind,
      message: options.message,
      expectsText: options.expectsText ?? false,
      createdAt: now.toISOString(),
      expiresAt: new Date(now.getTime() + options.timeoutMs).toISOString(),
    };

    return new Promise<OperatorAnswer>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.settle(request.id, null, new OperatorInputTimeoutError(request.id, request.kind));
      }, options.timeoutMs);

      this.pending.set(request.id, { request, resolve, reject, timer });

      options.signal?.addEventListener(
        'abort',
        () => this.settle(request.id, null, new OperatorInputCancelledError(request.id)),
        { once: true },
      );

      this.logger.warn(`Waiting for a person: ${request.message}`, {
        event: 'input.requested',
        jobId: request.jobId,
        accountId: request.accountId,
        kind: request.kind,
        requestId: request.id,
      });
      this.events.publish({ type: 'input.requested', timestamp: nowIso(), payload: request });
    });
  }

  answer(requestId: string, value: string, cancel: boolean): void {
    if (!this.pending.has(requestId)) throw new OperatorRequestNotFoundError(requestId);

    if (cancel) {
      this.settle(requestId, null, new OperatorInputCancelledError(requestId));
      return;
    }
    this.settle(requestId, { value, cancelled: false }, null);
  }

  list(): OperatorRequest[] {
    return [...this.pending.values()].map((entry) => entry.request);
  }

  /** Used on shutdown: nothing waiting can be answered any more. */
  cancelAll(): void {
    for (const id of [...this.pending.keys()]) {
      this.settle(id, null, new OperatorInputCancelledError(id));
    }
  }

  private settle(requestId: string, answer: OperatorAnswer | null, error: Error | null): void {
    const entry = this.pending.get(requestId);
    if (entry === undefined) return;

    this.pending.delete(requestId);
    clearTimeout(entry.timer);

    const cancelled = answer === null;
    this.events.publish({
      type: 'input.resolved',
      timestamp: nowIso(),
      payload: { requestId, jobId: entry.request.jobId, cancelled },
    });

    if (answer !== null) {
      entry.resolve(answer);
    } else {
      entry.reject(error ?? new OperatorInputCancelledError(requestId));
    }
  }
}
