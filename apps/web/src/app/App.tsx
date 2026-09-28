import type { ReactElement } from 'react';
import { RouterProvider } from 'react-router-dom';
import { AppProviders } from './providers';
import { router } from './router';

export const App = (): ReactElement => (
  <AppProviders>
    <RouterProvider router={router} future={{ v7_startTransition: true }} />
  </AppProviders>
);
