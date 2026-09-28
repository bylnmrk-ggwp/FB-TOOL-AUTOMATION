import type { Activity, ActivityKind, Group, GroupSummary } from '@fb/shared';
import type { Page, PageRequest } from '../shared/index.js';

export interface GroupFilter extends PageRequest {
  accountId?: string;
  search?: string;
}

export interface FetchedGroup {
  name: string;
  url: string;
}

export interface GroupRepository {
  list(filter: GroupFilter): Promise<Page<Group>>;
  /** Every distinct group url, with the accounts that belong to it. */
  summaries(): Promise<GroupSummary[]>;
  /** Replaces what is known for one account with what Facebook just showed. */
  replaceForAccount(accountId: string, groups: readonly FetchedGroup[]): Promise<number>;
  deleteByAccount(accountId: string): Promise<number>;
}

export interface NewActivity {
  id: string;
  accountId: string;
  kind: ActivityKind;
  targetUrl: string;
  targetName: string | null;
  status: Activity['status'];
  message: string | null;
  jobId: string | null;
}

/**
 * What each account has already done to a target. One row per account,
 * kind and target: recording the same share again overwrites the earlier
 * verdict rather than duplicating it.
 */
export interface ActivityRepository {
  record(activity: NewActivity): Promise<Activity>;
  find(accountId: string, kind: ActivityKind, targetUrl: string): Promise<Activity | null>;
  /** Targets this account has already completed, for skipping in a bulk run. */
  doneTargets(accountId: string, kind: ActivityKind): Promise<Set<string>>;
  listForAccount(accountId: string, limit: number): Promise<Activity[]>;
  deleteByAccount(accountId: string): Promise<number>;
}
