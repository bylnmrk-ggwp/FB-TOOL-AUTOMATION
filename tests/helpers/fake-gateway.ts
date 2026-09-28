import type { AutomationAction, AutomationResult } from '@fb/shared';
import type { AutomationContext, AutomationGateway } from '@fb/domain';

export interface RecordedExecution {
  action: AutomationAction;
  accountId: string;
  jobId: string;
  startedAt: number;
  finishedAt: number;
}

type Behaviour =
  | { kind: 'succeed' }
  | { kind: 'fail'; error: Error }
  | { kind: 'hang' }
  | { kind: 'delay'; ms: number };

/**
 * An automation gateway with no browser behind it. It records what it was
 * asked to do and can be told to fail, stall or take its time, which is what
 * the queue's interesting paths need.
 */
export class FakeGateway implements AutomationGateway {
  readonly executions: RecordedExecution[] = [];
  /** Consumed in order; the last one repeats once the list runs out. */
  private readonly script: Behaviour[] = [];
  private fallback: Behaviour = { kind: 'succeed' };

  /** Resolves once the given number of executions have started. */
  private startedCount = 0;
  private waiters: Array<{ count: number; resolve: () => void }> = [];

  alwaysSucceed(): this {
    this.fallback = { kind: 'succeed' };
    return this;
  }

  alwaysFail(error: Error): this {
    this.fallback = { kind: 'fail', error };
    return this;
  }

  thenFail(error: Error): this {
    this.script.push({ kind: 'fail', error });
    return this;
  }

  thenSucceed(): this {
    this.script.push({ kind: 'succeed' });
    return this;
  }

  thenHang(): this {
    this.script.push({ kind: 'hang' });
    return this;
  }

  thenDelay(ms: number): this {
    this.script.push({ kind: 'delay', ms });
    return this;
  }

  async execute(action: AutomationAction, context: AutomationContext): Promise<AutomationResult> {
    const startedAt = Date.now();
    this.startedCount += 1;
    this.settleWaiters();

    context.onProgress(50, 'halfway');

    const behaviour = this.script.shift() ?? this.fallback;

    if (behaviour.kind === 'fail') {
      this.record(action, context, startedAt);
      throw behaviour.error;
    }

    if (behaviour.kind === 'hang') {
      // Waits until the job is cancelled, which is how a stuck action behaves.
      await new Promise<void>((resolve) => {
        if (context.signal.aborted) {
          resolve();
          return;
        }
        context.signal.addEventListener('abort', () => resolve(), { once: true });
      });
      this.record(action, context, startedAt);
      throw new DOMException('The job was cancelled', 'AbortError');
    }

    if (behaviour.kind === 'delay') {
      await new Promise((resolve) => setTimeout(resolve, behaviour.ms));
    }

    this.record(action, context, startedAt);
    return {
      resourceUrl: 'https://example.invalid/posts/1',
      durationMs: Date.now() - startedAt,
      screenshotPath: null,
      details: { fake: true },
    };
  }

  /** Waits until `count` executions have begun. */
  async waitForStarts(count: number, timeoutMs = 5_000): Promise<void> {
    if (this.startedCount >= count) return;

    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error(`Only ${this.startedCount} of ${count} executions started`)),
        timeoutMs,
      );
      this.waiters.push({
        count,
        resolve: () => {
          clearTimeout(timer);
          resolve();
        },
      });
    });
  }

  private settleWaiters(): void {
    const ready = this.waiters.filter((waiter) => waiter.count <= this.startedCount);
    this.waiters = this.waiters.filter((waiter) => waiter.count > this.startedCount);
    for (const waiter of ready) waiter.resolve();
  }

  private record(action: AutomationAction, context: AutomationContext, startedAt: number): void {
    this.executions.push({
      action,
      accountId: context.accountId,
      jobId: context.jobId,
      startedAt,
      finishedAt: Date.now(),
    });
  }
}
