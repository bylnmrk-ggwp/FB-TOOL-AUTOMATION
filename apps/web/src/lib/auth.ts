const STORAGE_KEY = 'fb.auth.token';

const listeners = new Set<() => void>();

export const getToken = (): string | null => {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
};

export const setToken = (token: string): void => {
  try {
    localStorage.setItem(STORAGE_KEY, token);
  } catch {
    // Private window or storage disabled: the session lasts until reload.
  }
};

export const clearToken = (): void => {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing stored, nothing to clear.
  }
};

/** Headers to merge into any fetch that reaches the API. Empty when signed out. */
export const authHeaders = (): Record<string, string> => {
  const token = getToken();
  return token === null ? {} : { authorization: `Bearer ${token}` };
};

/** Called when the server answers AUTH_REQUIRED: the stored token is gone. */
export const onUnauthorized = (listener: () => void): (() => void) => {
  listeners.add(listener);
  return () => listeners.delete(listener);
};

export const reportUnauthorized = (): void => {
  clearToken();
  for (const listener of listeners) listener();
};
