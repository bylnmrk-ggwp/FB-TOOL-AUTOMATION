import type { StorageState } from '@fb/shared';

/**
 * Moving a signed-in session between machines. Both directions work on the
 * profile directory, so the browser for that account must not be running.
 */
export interface SessionTransferPort {
  /** Reads cookies and local storage out of a profile without visiting Facebook. */
  exportState(
    userDataDir: string,
    channel: string,
    executablePath: string | null,
  ): Promise<StorageState>;
  /** Writes a state into a profile, replacing whatever session it had. */
  importState(
    userDataDir: string,
    channel: string,
    executablePath: string | null,
    state: StorageState,
  ): Promise<void>;
}

/** A row source for the roster: a Google Sheet, a workbook, a CSV. */
export interface RosterSource {
  /** Every row including the header, as strings; missing trailing cells absent. */
  readRows(): Promise<string[][]>;
  describe(): string;
}
