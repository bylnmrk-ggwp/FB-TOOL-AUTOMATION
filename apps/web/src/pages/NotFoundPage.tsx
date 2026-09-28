import type { ReactElement } from 'react';
import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/common/Feedback';

export const NotFoundPage = (): ReactElement => (
  <EmptyState
    title="There is no page here"
    description="The address may be old, or mistyped."
    action={
      <Button asChild>
        <Link to="/">Back to the dashboard</Link>
      </Button>
    }
  />
);
