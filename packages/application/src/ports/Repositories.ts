import type {
  AccountRepository,
  ActivityRepository,
  BrowserProfileRepository,
  GroupRepository,
  JobRepository,
  LogRepository,
  SettingsRepository,
} from '@fb/domain';

/** The persistence surface a use case may reach for. */
export interface Repositories {
  accounts: AccountRepository;
  profiles: BrowserProfileRepository;
  jobs: JobRepository;
  logs: LogRepository;
  settings: SettingsRepository;
  groups: GroupRepository;
  activities: ActivityRepository;
}
