/**
 * One job per account at a time.
 *
 * This is an in-process guard, and that is enough: the profile lock in the
 * database is what stops a second *process* from touching the same browser,
 * while this stops two workers inside one process from queueing up behind each
 * other's clicks.
 */
export class AccountLockManager {
  private readonly held = new Map<string, { since: Date; jobId: string }>();

  tryAcquire(accountId: string, jobId: string): boolean {
    if (this.held.has(accountId)) return false;
    this.held.set(accountId, { since: new Date(), jobId });
    return true;
  }

  release(accountId: string): void {
    this.held.delete(accountId);
  }

  isHeld(accountId: string): boolean {
    return this.held.has(accountId);
  }

  heldAccountIds(): string[] {
    return [...this.held.keys()];
  }

  jobHolding(accountId: string): string | null {
    return this.held.get(accountId)?.jobId ?? null;
  }

  size(): number {
    return this.held.size;
  }

  clear(): void {
    this.held.clear();
  }
}
