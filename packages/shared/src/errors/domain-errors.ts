import { AppError } from './AppError.js';
import { ERROR_CODES } from './codes.js';

// --- Accounts --------------------------------------------------------------

export class AccountNotFoundError extends AppError {
  constructor(accountId: string) {
    super(ERROR_CODES.ACCOUNT_NOT_FOUND, `Account ${accountId} does not exist`, {
      status: 404,
      details: { accountId },
    });
  }
}

export class AccountDisabledError extends AppError {
  constructor(accountId: string) {
    super(ERROR_CODES.ACCOUNT_DISABLED, `Account ${accountId} is disabled`, {
      status: 409,
      details: { accountId },
    });
  }
}

export class AccountNameTakenError extends AppError {
  constructor(name: string) {
    super(ERROR_CODES.ACCOUNT_NAME_TAKEN, `An account named "${name}" already exists`, {
      status: 409,
      details: { name },
    });
  }
}

export class AccountBusyError extends AppError {
  constructor(accountId: string) {
    super(ERROR_CODES.ACCOUNT_BUSY, `Account ${accountId} is busy with another job`, {
      status: 409,
      details: { accountId },
      retryable: true,
    });
  }
}

// --- Browser profiles ------------------------------------------------------

export class ProfileNotFoundError extends AppError {
  constructor(profileId: string) {
    super(ERROR_CODES.PROFILE_NOT_FOUND, `Browser profile ${profileId} does not exist`, {
      status: 404,
      details: { profileId },
    });
  }
}

export class ProfileLockedError extends AppError {
  constructor(profileId: string, holder: string) {
    super(ERROR_CODES.PROFILE_LOCKED, `Browser profile ${profileId} is locked by ${holder}`, {
      status: 409,
      details: { profileId, holder },
      retryable: true,
    });
  }
}

export class ProfilePathInvalidError extends AppError {
  constructor(path: string) {
    super(ERROR_CODES.PROFILE_PATH_INVALID, 'Profile path escapes the configured profile root', {
      status: 400,
      details: { path },
    });
  }
}

// --- Browser sessions ------------------------------------------------------

export class BrowserAlreadyRunningError extends AppError {
  constructor(accountId: string) {
    super(ERROR_CODES.BROWSER_ALREADY_RUNNING, `A browser is already running for ${accountId}`, {
      status: 409,
      details: { accountId },
    });
  }
}

export class BrowserNotRunningError extends AppError {
  constructor(accountId: string) {
    super(ERROR_CODES.BROWSER_NOT_RUNNING, `No browser is running for ${accountId}`, {
      status: 409,
      details: { accountId },
    });
  }
}

export class BrowserLaunchError extends AppError {
  constructor(accountId: string, reason: string, cause?: unknown) {
    super(ERROR_CODES.BROWSER_LAUNCH_FAILED, `Could not launch a browser for ${accountId}`, {
      status: 500,
      details: { accountId, reason },
      cause,
      retryable: true,
    });
  }
}

export class BrowserCrashedError extends AppError {
  constructor(accountId: string, cause?: unknown) {
    super(ERROR_CODES.BROWSER_CRASHED, `The browser for ${accountId} closed unexpectedly`, {
      status: 500,
      details: { accountId },
      cause,
      retryable: true,
    });
  }
}

// --- Automation ------------------------------------------------------------

export class AutomationTimeoutError extends AppError {
  constructor(step: string, timeoutMs: number) {
    super(ERROR_CODES.AUTOMATION_TIMEOUT, `Step "${step}" timed out after ${timeoutMs}ms`, {
      status: 504,
      details: { step, timeoutMs },
      retryable: true,
    });
  }
}

export class AutomationFailedError extends AppError {
  constructor(message: string, details?: unknown, cause?: unknown) {
    super(ERROR_CODES.AUTOMATION_FAILED, message, {
      status: 500,
      details,
      cause,
      retryable: true,
    });
  }
}

export class NotLoggedInError extends AppError {
  constructor(accountId: string) {
    super(ERROR_CODES.AUTOMATION_NOT_LOGGED_IN, `Account ${accountId} is not logged in`, {
      status: 409,
      details: { accountId },
      // A human has to sign in inside the persistent profile, so retrying is pointless.
      retryable: false,
    });
  }
}

export class SelectorMissingError extends AppError {
  constructor(selectorName: string, url: string) {
    super(ERROR_CODES.AUTOMATION_SELECTOR_MISSING, `Could not find "${selectorName}" on the page`, {
      status: 500,
      details: { selectorName, url },
      retryable: true,
    });
  }
}

export class AutomationBlockedError extends AppError {
  constructor(reason: string) {
    super(ERROR_CODES.AUTOMATION_BLOCKED, `The action was blocked: ${reason}`, {
      status: 409,
      details: { reason },
      retryable: false,
    });
  }
}

// --- Jobs ------------------------------------------------------------------

export class JobNotFoundError extends AppError {
  constructor(jobId: string) {
    super(ERROR_CODES.JOB_NOT_FOUND, `Job ${jobId} does not exist`, {
      status: 404,
      details: { jobId },
    });
  }
}

export class JobAlreadyRunningError extends AppError {
  constructor(jobId: string) {
    super(ERROR_CODES.JOB_ALREADY_RUNNING, `Job ${jobId} is already running`, {
      status: 409,
      details: { jobId },
    });
  }
}

export class JobNotCancellableError extends AppError {
  constructor(jobId: string, status: string) {
    super(ERROR_CODES.JOB_NOT_CANCELLABLE, `Job ${jobId} cannot be cancelled while ${status}`, {
      status: 409,
      details: { jobId, status },
    });
  }
}

export class JobNotRetryableError extends AppError {
  constructor(jobId: string, status: string) {
    super(ERROR_CODES.JOB_NOT_RETRYABLE, `Job ${jobId} cannot be retried while ${status}`, {
      status: 409,
      details: { jobId, status },
    });
  }
}

export class JobCancelledError extends AppError {
  constructor(jobId: string) {
    super(ERROR_CODES.JOB_CANCELLED, `Job ${jobId} was cancelled`, {
      status: 409,
      details: { jobId },
      retryable: false,
    });
  }
}

export class InvalidJobTransitionError extends AppError {
  constructor(jobId: string, from: string, to: string) {
    super(ERROR_CODES.INVALID_JOB_TRANSITION, `Job ${jobId} cannot move from ${from} to ${to}`, {
      status: 409,
      details: { jobId, from, to },
    });
  }
}

// --- Storage ---------------------------------------------------------------

export class FileNotFoundError extends AppError {
  constructor(fileId: string) {
    super(ERROR_CODES.FILE_NOT_FOUND, `File ${fileId} does not exist`, {
      status: 404,
      details: { fileId },
    });
  }
}

export class PathTraversalError extends AppError {
  constructor(attempted: string) {
    super(ERROR_CODES.PATH_TRAVERSAL, 'The requested path is outside the allowed directory', {
      status: 400,
      details: { attempted },
    });
  }
}

export class UnsupportedMediaTypeError extends AppError {
  constructor(mimeType: string) {
    super(ERROR_CODES.UNSUPPORTED_MEDIA_TYPE, `Files of type ${mimeType} are not accepted`, {
      status: 415,
      details: { mimeType },
    });
  }
}

// --- Settings --------------------------------------------------------------

export class SettingsInvalidError extends AppError {
  constructor(problems: string[]) {
    super(ERROR_CODES.SETTINGS_INVALID, 'The settings are not valid', {
      status: 400,
      details: { problems },
    });
  }
}

// --- Credentials, gates and the operator --------------------------------

export class CredentialsMissingError extends AppError {
  constructor(accountId: string) {
    super(
      ERROR_CODES.ACCOUNT_CREDENTIALS_MISSING,
      `Account ${accountId} has no username and password to sign in with`,
      { status: 409, details: { accountId }, retryable: false },
    );
  }
}

export class ShareRestrictedError extends AppError {
  constructor(accountId: string, until: string | null) {
    super(
      ERROR_CODES.ACCOUNT_SHARE_RESTRICTED,
      `Facebook is restricting account ${accountId} from sharing`,
      { status: 409, details: { accountId, until }, retryable: false },
    );
  }
}

export class LoginFailedError extends AppError {
  constructor(reason: string, retryable = false) {
    super(ERROR_CODES.AUTOMATION_LOGIN_FAILED, `Login failed: ${reason}`, {
      status: 409,
      details: { reason },
      retryable,
    });
  }
}

/** Facebook put a checkpoint, code prompt or confirmation in the way. */
export class AccountGatedError extends AppError {
  constructor(gate: string, message: string) {
    super(ERROR_CODES.AUTOMATION_GATED, message, {
      status: 409,
      details: { gate },
      // A person has to clear it; another automatic attempt hits the same wall.
      retryable: false,
    });
  }
}

export class OperatorInputTimeoutError extends AppError {
  constructor(requestId: string, kind: string) {
    super(ERROR_CODES.OPERATOR_INPUT_TIMEOUT, `Nobody answered the ${kind} request in time`, {
      status: 408,
      details: { requestId, kind },
      retryable: false,
    });
  }
}

export class OperatorInputCancelledError extends AppError {
  constructor(requestId: string) {
    super(ERROR_CODES.OPERATOR_INPUT_CANCELLED, 'The operator cancelled this step', {
      status: 409,
      details: { requestId },
      retryable: false,
    });
  }
}

export class OperatorRequestNotFoundError extends AppError {
  constructor(requestId: string) {
    super(ERROR_CODES.OPERATOR_REQUEST_NOT_FOUND, `Request ${requestId} is not waiting`, {
      status: 404,
      details: { requestId },
    });
  }
}

export class GroupNotFoundError extends AppError {
  constructor(name: string) {
    super(ERROR_CODES.GROUP_NOT_FOUND, `No group matching "${name}" was found`, {
      status: 404,
      details: { name },
      retryable: false,
    });
  }
}

export class WorkbookInvalidError extends AppError {
  constructor(reason: string) {
    super(ERROR_CODES.WORKBOOK_INVALID, `The workbook could not be read: ${reason}`, {
      status: 400,
      details: { reason },
    });
  }
}
