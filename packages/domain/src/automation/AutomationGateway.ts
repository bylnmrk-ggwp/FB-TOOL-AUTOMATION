import type {
  AutomationAction,
  AutomationResult,
  InputKind,
  OperatorAnswer,
  Settings,
} from '@fb/shared';

/** A random pause drawn from one of the configured ranges. */
export type DelayName =
  'step' | 'betweenShares' | 'afterShareButton' | 'afterPost' | 'betweenJoins' | 'afterComment';

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
  /** The anti-spam ranges, as the operator set them. */
  settings: Settings;
  /**
   * Stops the job and asks a person. Resolves when they answer, rejects when
   * they cancel or nobody answers in time. The browser window stays open, so
   * "answer" often means "I did it in the window".
   */
  askOperator: (request: {
    kind: InputKind;
    message: string;
    expectsText?: boolean;
  }) => Promise<OperatorAnswer>;
}

/**
 * The single seam between the queue and any real automation. Swapping this for
 * a fake is what makes the queue testable without a browser.
 */
export interface AutomationGateway {
  execute(action: AutomationAction, context: AutomationContext): Promise<AutomationResult>;
}
