import type { ReactElement } from 'react';
import { RouterProvider } from 'react-router-dom';
import { AuthGate } from '../features/auth/AuthGate';
import { AppProviders } from './providers';
import { router } from './router';

export const App = (): ReactElement => (
  <AppProviders>
    <AuthGate>
      <RouterProvider router={router} future={{ v7_startTransition: true }} />
    </AuthGate>
  </AppProviders>
);
