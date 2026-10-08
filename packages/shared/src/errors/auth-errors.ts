import { AppError } from './AppError.js';
import { ERROR_CODES } from './codes.js';

/** No token, or a token that does not verify. The client should show the login page. */
export class AuthRequiredError extends AppError {
  constructor() {
    super(ERROR_CODES.AUTH_REQUIRED, 'Sign in to use the control panel', { status: 401 });
  }
}

/** A login attempt with the wrong password. */
export class AuthInvalidError extends AppError {
  constructor() {
    super(ERROR_CODES.AUTH_INVALID, 'Wrong password', { status: 401 });
  }
}

/** Too many wrong passwords in a row. */
export class AuthRateLimitedError extends AppError {
  constructor(retryAfterSeconds: number) {
    super(
      ERROR_CODES.AUTH_RATE_LIMITED,
      `Too many failed logins; try again in ${Math.ceil(retryAfterSeconds / 60)} minute(s)`,
      { status: 429, details: { retryAfterSeconds } },
    );
  }
}
