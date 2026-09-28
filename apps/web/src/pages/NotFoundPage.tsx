import type { ReactElement } from 'react';
import { Link } from 'react-router-dom';

export const NotFoundPage = (): ReactElement => (
  <div>
    <h1>Page not found</h1>
    <p>
      <Link to="/">Back to the dashboard</Link>
    </p>
  </div>
);
