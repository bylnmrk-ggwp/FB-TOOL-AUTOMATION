import { nowIso, type Group, type GroupSummary } from '@fb/shared';
import type { FetchedGroup, GroupFilter, Page } from '@fb/domain';
import type { EventPublisher } from '../ports/EventPublisher.js';
import type { Logger } from '../ports/Logger.js';
import type { Repositories } from '../ports/Repositories.js';

/** Groups are read from Facebook by a job and kept here for the pickers. */
export class GroupService {
  constructor(
    private readonly repositories: Repositories,
    private readonly events: EventPublisher,
    private readonly logger: Logger,
  ) {}

  list(filter: GroupFilter): Promise<Page<Group>> {
    return this.repositories.groups.list(filter);
  }

  summaries(): Promise<GroupSummary[]> {
    return this.repositories.groups.summaries();
  }

  /** Called by the queue when a fetch_groups job finishes. */
  async recordFetched(accountId: string, groups: readonly FetchedGroup[]): Promise<number> {
    const count = await this.repositories.groups.replaceForAccount(accountId, groups);
    this.logger.info(`Recorded ${count} group(s)`, { event: 'groups.fetched', accountId });
    this.events.publish({
      type: 'groups.changed',
      timestamp: nowIso(),
      payload: { accountId, count },
    });
    return count;
  }
}
