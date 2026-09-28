import { useState, type ReactElement } from 'react';
import { HandHelping } from 'lucide-react';
import { toast } from 'sonner';
import type { OperatorRequest } from '@fb/shared';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { errorMessage } from '@/components/common/Feedback';
import { useAnswerOperatorRequest, useOperatorRequests } from '../../groups/hooks';
import { relativeTime } from '../../../lib/format';

const KIND_LABEL: Record<OperatorRequest['kind'], string> = {
  captcha: 'Captcha',
  two_factor: 'Two-factor code',
  checkpoint: 'Checkpoint',
  confirm: 'Confirmation',
  text: 'Input',
};

/**
 * Jobs that have stopped and are waiting for a person. Each card is one
 * request; answering it lets that job continue, cancelling fails it. The
 * browser window on the PC is where the actual solving happens — this only
 * tells the job that it is done.
 */
export const OperatorPrompts = ({
  accountName,
}: {
  accountName: (id: string) => string;
}): ReactElement | null => {
  const requests = useOperatorRequests();
  const answer = useAnswerOperatorRequest();
  const [values, setValues] = useState<Record<string, string>>({});

  const pending = requests.data ?? [];
  if (pending.length === 0) return null;

  const respond = (request: OperatorRequest, cancel: boolean): void => {
    answer.mutate(
      { requestId: request.id, value: values[request.id] ?? '', cancel },
      {
        onError: (error) => toast.error(errorMessage(error)),
        onSuccess: () => toast.success(cancel ? 'Job cancelled' : 'Answer sent; the job continues'),
      },
    );
  };

  return (
    <section
      className="grid gap-3 rounded-lg border border-warning/50 bg-warning/5 p-4"
      aria-live="polite"
    >
      <div className="flex items-center gap-2 text-sm font-medium">
        <HandHelping className="size-4 text-warning" aria-hidden="true" />
        {pending.length === 1
          ? 'A job is waiting for you'
          : `${pending.length} jobs are waiting for you`}
      </div>

      <ul className="grid gap-3">
        {pending.map((request) => (
          <li key={request.id} className="grid gap-2 rounded-md border bg-card p-3 text-sm">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="font-medium">
                {KIND_LABEL[request.kind]} — {accountName(request.accountId)}
              </span>
              <span className="text-xs text-muted-foreground">
                asked {relativeTime(request.createdAt)}, expires {relativeTime(request.expiresAt)}
              </span>
            </div>
            <p className="text-muted-foreground">{request.message}</p>

            {request.expectsText && (
              <Input
                aria-label="Answer"
                placeholder="Type the answer"
                value={values[request.id] ?? ''}
                onChange={(event) =>
                  setValues((state) => ({ ...state, [request.id]: event.target.value }))
                }
              />
            )}

            <div className="flex justify-end gap-2">
              <Button
                size="sm"
                variant="ghost"
                onClick={() => respond(request, true)}
                disabled={answer.isPending}
              >
                Give up on this job
              </Button>
              <Button size="sm" onClick={() => respond(request, false)} disabled={answer.isPending}>
                {request.expectsText ? 'Send answer' : 'Done, continue'}
              </Button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
};
