import { useCallback, useEffect, type ReactElement, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { ErrorNotice } from '@/components/common/Feedback';
import { onUnauthorized } from '../../lib/auth';
import { LoginPage } from '../../pages/Login';
import { useSession } from './hooks';

/**
 * Decides between the login page and the app, once per page load. A 401 from
 * anywhere in the app clears the token and brings the login page back.
 */
export const AuthGate = ({ children }: { children: ReactNode }): ReactElement => {
  const queryClient = useQueryClient();
  const session = useSession();

  const refresh = useCallback((): void => {
    void queryClient.invalidateQueries({ queryKey: ['auth-session'] });
  }, [queryClient]);

  useEffect(
    () =>
      onUnauthorized(() => {
        // Everything cached was fetched with the token that just died.
        queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== 'auth-session' });
        refresh();
      }),
    [queryClient, refresh],
  );

  if (session.isPending) return <div className="min-h-svh bg-background" aria-busy="true" />;
  if (session.isError) {
    return (
      <main className="flex min-h-svh items-center justify-center bg-background p-4">
        <div className="w-full max-w-sm">
          <ErrorNotice error={session.error} title="PC unreachable" />
        </div>
      </main>
    );
  }
  if (session.data.authRequired && !session.data.authenticated) {
    return <LoginPage onSignedIn={refresh} />;
  }
  return <>{children}</>;
};
