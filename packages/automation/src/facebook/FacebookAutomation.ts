import type { BrowserContext } from 'playwright';
import {
  assertNever,
  AutomationFailedError,
  BrowserNotRunningError,
  CredentialsMissingError,
  JobCancelledError,
  type AutomationAction,
  type AutomationResult,
} from '@fb/shared';
import type { AccountCredentials, AutomationContext, AutomationGateway } from '@fb/domain';
import type { FileStore, Logger } from '@fb/application';
import { BrowserContextManager } from '../browser/BrowserContextManager.js';
import { FacebookNavigation } from './FacebookNavigation.js';
import { FacebookSession } from './FacebookSession.js';
import { comment } from './actions/comment.js';
import { createPost } from './actions/createPost.js';
import { acceptFriendRequestsAction, addFriendsAction } from './actions/friends.js';
import { fetchGroups, joinGroup } from './actions/groups.js';
import { checkLogin, login } from './actions/login.js';
import { autoSetupProfile } from './actions/profile.js';
import { reactToPost } from './actions/reactToPost.js';
import { sendMessage } from './actions/sendMessage.js';
import { sharePost } from './actions/sharePost.js';
import { shareToGroup } from './actions/shareToGroup.js';
import { uploadMedia } from './actions/uploadMedia.js';
import { watchLive } from './actions/watchLive.js';
import type { ActionContext } from './actions/types.js';

/** Supplies the live context for an account. BrowserManager satisfies this. */
export interface ContextProvider {
  contextFor(accountId: string): BrowserContext | null;
}

/** The login action needs a password; nothing else does. */
export interface CredentialSource {
  credentials(accountId: string): Promise<AccountCredentials | null>;
}

export interface FacebookAutomationDeps {
  contexts: ContextProvider;
  files: FileStore;
  logger: Logger;
  credentials: CredentialSource;
}

/**
 * The Facebook implementation of the automation gateway.
 *
 * It dispatches and nothing else: each action owns its own steps, in its own
 * file. Keeping the dispatch free of step logic is what stops this class from
 * growing into the thousand-line file that every browser automation project
 * ends up with.
 */
export class FacebookAutomation implements AutomationGateway {
  private readonly contextManager = new BrowserContextManager();

  constructor(private readonly deps: FacebookAutomationDeps) {}

  async execute(
    action: AutomationAction,
    automation: AutomationContext,
  ): Promise<AutomationResult> {
    const browserContext = this.deps.contexts.contextFor(automation.accountId);
    if (browserContext === null) throw new BrowserNotRunningError(automation.accountId);

    const page = await this.contextManager.activePage(browserContext);
    const navigation = new FacebookNavigation({
      timeoutMs: automation.timeoutMs,
      delayRangeMs: automation.delayRangeMs,
    });

    const log = this.deps.logger.child({
      jobId: automation.jobId,
      accountId: automation.accountId,
      sessionId: automation.sessionId,
      event: `automation.${action.type}`,
    });

    const context: ActionContext = {
      page,
      navigation,
      session: new FacebookSession(navigation),
      files: this.deps.files,
      automation,
      log: (message) => log.debug(message),
    };
    log.debug(`Running ${action.type}`);

    try {
      return await this.dispatch(action, context);
    } catch (error) {
      // An aborted action is a cancellation, not a failure; the queue has to
      // be able to tell them apart.
      if (isAbort(error)) throw new JobCancelledError(automation.jobId);
      if (error instanceof Error && error.name === 'TimeoutError') {
        throw new AutomationFailedError(error.message, { action: action.type }, error);
      }
      throw error;
    }
  }

  private async dispatch(
    action: AutomationAction,
    context: ActionContext,
  ): Promise<AutomationResult> {
    switch (action.type) {
      case 'create_post':
        return createPost(context, {
          text: action.text,
          media: action.media,
          audience: action.audience,
        });
      case 'upload_media':
        return uploadMedia(context, {
          targetUrl: action.targetUrl,
          media: action.media,
          ...(action.caption === undefined ? {} : { caption: action.caption }),
        });
      case 'comment':
        return comment(context, { postUrl: action.postUrl, text: action.text });
      case 'react_to_post':
        return reactToPost(context, { postUrl: action.postUrl, reaction: action.reaction });
      case 'send_message':
        return sendMessage(context, {
          threadId: action.threadId,
          text: action.text,
          media: action.media,
        });
      case 'share_post':
        return sharePost(context, {
          postUrl: action.postUrl,
          targets: action.targets,
          reaction: action.reaction,
          comments: action.comments,
        });
      case 'share_to_group':
        return shareToGroup(context, {
          postUrl: action.postUrl,
          groupName: action.groupName,
          groupUrl: action.groupUrl,
          shareToTimeline: action.shareToTimeline,
          reaction: action.reaction,
          comments: action.comments,
        });
      case 'join_group':
        return joinGroup(context, { groupUrl: action.groupUrl });
      case 'fetch_groups':
        return fetchGroups(context);
      case 'login': {
        const credentials = await this.deps.credentials.credentials(context.automation.accountId);
        if (credentials === null) throw new CredentialsMissingError(context.automation.accountId);
        return login(context, { credentials, waitForOperator: action.waitForOperator });
      }
      case 'check_login':
        return checkLogin(context);
      case 'accept_friend_requests':
        return acceptFriendRequestsAction(context, { max: action.max });
      case 'add_friends':
        return addFriendsAction(context, { target: action.target });
      case 'auto_setup_profile':
        return autoSetupProfile(context, {
          targetFriends: action.targetFriends,
          connectFriends: action.connectFriends,
          bio: action.bio,
          profilePicture: action.profilePicture,
        });
      case 'watch_live':
        return watchLive(context, { url: action.url, minutes: action.minutes });
      default:
        return assertNever(action, 'Unsupported automation action');
    }
  }
}

const isAbort = (error: unknown): boolean =>
  error instanceof Error && (error.name === 'AbortError' || error.message.includes('cancelled'));
