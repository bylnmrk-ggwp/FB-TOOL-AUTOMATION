import type { AutomationAction, AutomationResult } from '@fb/shared';

export interface AutomationContext {
  jobId: string;
  accountId: string;
  sessionId: string;
  /** Fires while a step finishes so the queue can publish progress. */
  onProgress: (progress: number, step: string) => void;
  /** Resolves true once the job has been cancelled; the gateway then aborts. */
  signal: AbortSignal;
  timeoutMs: number;
  /** Idle range inserted between steps, in milliseconds. */
  delayRangeMs: readonly [number, number];
}

/**
 * The single seam between the queue and any real automation. Swapping this for
 * a fake is what makes the queue testable without a browser.
 */
export interface AutomationGateway {
  execute(action: AutomationAction, context: AutomationContext): Promise<AutomationResult>;
}
