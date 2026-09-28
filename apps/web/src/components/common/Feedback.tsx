import type { ReactElement, ReactNode } from 'react';
import { AlertCircle, Info } from 'lucide-react';
import { AppError } from '@fb/shared';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';

/** Turns any thrown value into something worth showing a person. */
export const errorMessage = (error: unknown): string => {
  if (error instanceof AppError) return error.message;
  if (error instanceof Error) return error.message;
  return 'Something went wrong';
};

export const ErrorNotice = ({
  error,
  title = 'That did not work',
}: {
  error: unknown;
  title?: string;
}): ReactElement => (
  <Alert variant="destructive" role="alert">
    <AlertCircle />
    <AlertTitle>{title}</AlertTitle>
    <AlertDescription>{errorMessage(error)}</AlertDescription>
  </Alert>
);

/** Guidance, not a problem: announced politely, never as an alert. */
export const InfoNotice = ({ children }: { children: ReactNode }): ReactElement => (
  <Alert role="status">
    <Info />
    <AlertDescription>{children}</AlertDescription>
  </Alert>
);

/** Rows of placeholder text where a table or list is about to appear. */
export const Loading = ({ rows = 3 }: { rows?: number }): ReactElement => (
  <div className="space-y-2" aria-busy="true" aria-live="polite">
    {Array.from({ length: rows }, (_, index) => (
      <Skeleton key={index} className="h-9 w-full" />
    ))}
  </div>
);

export const EmptyState = ({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}): ReactElement => (
  <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed px-6 py-12 text-center">
    <p className="font-medium">{title}</p>
    {description !== undefined && (
      <p className="max-w-[44ch] text-sm text-muted-foreground">{description}</p>
    )}
    {action !== undefined && <div className="mt-2">{action}</div>}
  </div>
);
