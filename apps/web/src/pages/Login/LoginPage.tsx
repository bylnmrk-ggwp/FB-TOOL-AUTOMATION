import { useState, type FormEvent, type ReactElement } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ErrorNotice } from '@/components/common/Feedback';
import { TextField } from '@/components/forms/Field';
import { login } from '../../api/auth';
import { setToken } from '../../lib/auth';

/** One password for the one operator. The server rate-limits wrong guesses. */
export const LoginPage = ({ onSignedIn }: { onSignedIn: () => void }): ReactElement => {
  const [password, setPassword] = useState('');
  const attempt = useMutation({
    mutationFn: login,
    onSuccess: ({ token }) => {
      setToken(token);
      onSignedIn();
    },
  });

  const submit = (event: FormEvent): void => {
    event.preventDefault();
    if (password.length === 0 || attempt.isPending) return;
    attempt.mutate(password);
  };

  return (
    <main className="flex min-h-svh items-center justify-center bg-background p-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>FB Automation</CardTitle>
          <CardDescription>Enter the control panel password.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="grid gap-4" onSubmit={submit}>
            <TextField
              label="Password"
              type="password"
              autoComplete="current-password"
              autoFocus
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            {attempt.error !== null && <ErrorNotice error={attempt.error} title="Not signed in" />}
            <Button type="submit" disabled={password.length === 0 || attempt.isPending}>
              {attempt.isPending ? 'Signing in…' : 'Sign in'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
};
