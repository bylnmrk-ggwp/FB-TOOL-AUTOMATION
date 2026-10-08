/**
 * Counts failed logins in a sliding window. One counter for the whole
 * server: there is a single operator, and a global count cannot be sidestepped
 * with forged forwarding headers the way a per-address count can.
 */
export class LoginRateLimiter {
  private readonly limit: number;
  private readonly windowMs: number;
  private failures: number[] = [];

  constructor(options: { limit?: number; windowMs?: number } = {}) {
    this.limit = options.limit ?? 5;
    this.windowMs = options.windowMs ?? 15 * 60 * 1000;
  }

  private prune(nowMs: number): void {
    this.failures = this.failures.filter((at) => nowMs - at < this.windowMs);
  }

  isLimited(nowMs: number): boolean {
    this.prune(nowMs);
    return this.failures.length >= this.limit;
  }

  /** Milliseconds until the oldest failure in the window ages out; 0 when not limited. */
  retryAfterMs(nowMs: number): number {
    if (!this.isLimited(nowMs)) return 0;
    const oldest = this.failures[0];
    return oldest === undefined ? 0 : Math.max(0, oldest + this.windowMs - nowMs);
  }

  recordFailure(nowMs: number): void {
    this.prune(nowMs);
    this.failures.push(nowMs);
  }

  reset(): void {
    this.failures = [];
  }
}
