import type { Page } from 'playwright';
import type { AutomationContext } from '@fb/domain';
import type { FileStore } from '@fb/application';
import type { FacebookNavigation } from '../FacebookNavigation.js';
import type { FacebookSession } from '../FacebookSession.js';

/** What every action is handed. Actions never reach outside this. */
export interface ActionContext {
  page: Page;
  navigation: FacebookNavigation;
  session: FacebookSession;
  /** Resolves a media id to a path inside the upload directory. */
  files: FileStore;
  automation: AutomationContext;
}

/**
 * Aborts the action if the job has been cancelled. Called between steps, which
 * is where a cancellation can take effect without leaving a half-typed post.
 */
export const throwIfCancelled = (context: ActionContext): void => {
  if (context.automation.signal.aborted) {
    throw new DOMException('The job was cancelled', 'AbortError');
  }
};

/** Reports a step to the queue, which forwards it to the UI. */
export const step = (context: ActionContext, progress: number, description: string): void => {
  context.automation.onProgress(progress, description);
};
