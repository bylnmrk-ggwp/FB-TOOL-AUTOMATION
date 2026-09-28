import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState, type ReactElement, type ReactNode } from 'react';
import { AppError } from '@fb/shared';

/** A 4xx means the request was wrong; repeating it will not help. */
const shouldRetry = (failureCount: number, error: unknown): boolean => {
  if (error instanceof AppError && error.status < 500) return false;
  return failureCount < 2;
};

export const AppProviders = ({ children }: { children: ReactNode }): ReactElement => {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 5_000,
            refetchOnWindowFocus: false,
            retry: shouldRetry,
          },
          mutations: { retry: false },
        },
      }),
  );

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
};
