import { useEffect, useState, type FormEvent, type ReactElement } from 'react';
import { toast } from 'sonner';
import {
  BROWSER_CHANNELS,
  DELAY_RANGES,
  SettingsSchema,
  validateSettings,
  type Settings,
} from '@fb/shared';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ErrorNotice, Loading } from '@/components/common/Feedback';
import { PageHeader } from '@/components/common/PageHeader';
import { CheckboxField, SelectField, TextField } from '@/components/forms/Field';
import { useSettings, useSystemPaths, useUpdateSettings } from '../../features/settings/hooks';

/** Seconds in the form, milliseconds in the API: nobody thinks in 15000. */
const seconds = (ms: number): string => String(Math.round(ms / 100) / 10);
const fromSeconds = (value: string, fallback: number): number => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.round(parsed * 1000) : fallback;
};

export const SettingsPage = (): ReactElement => {
  const settings = useSettings();
  const paths = useSystemPaths();
  const update = useUpdateSettings();

  const [draft, setDraft] = useState<Settings | null>(null);
  const [problems, setProblems] = useState<string[]>([]);

  useEffect(() => {
    if (settings.data !== undefined && draft === null) setDraft(settings.data);
  }, [settings.data, draft]);

  if (settings.isError) return <ErrorNotice error={settings.error} />;
  if (settings.isPending || draft === null) return <Loading rows={6} />;

  const set = <K extends keyof Settings>(key: K, value: Settings[K]): void =>
    setDraft((state) => (state === null ? state : { ...state, [key]: value }));

  const number = (value: string, fallback: number): number => {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  };

  const submit = (event: FormEvent): void => {
    event.preventDefault();

    const parsed = SettingsSchema.safeParse(draft);
    if (!parsed.success) {
      setProblems(parsed.error.issues.map((issue) => `${issue.path.join('.')}: ${issue.message}`));
      return;
    }
    const crossField = validateSettings(parsed.data);
    if (crossField.length > 0) {
      setProblems(crossField);
      return;
    }

    setProblems([]);
    update.mutate(parsed.data, {
      onSuccess: (next) => {
        setDraft(next);
        toast.success('Settings saved');
      },
    });
  };

  const dirty = JSON.stringify(draft) !== JSON.stringify(settings.data);

  return (
    <div className="grid gap-6">
      <PageHeader
        title="Settings"
        description="Applied to the next browser and the next queue pass. No restart needed."
      />

      <form className="grid gap-4" onSubmit={submit}>
        <Card>
          <CardHeader>
            <CardTitle>Browser</CardTitle>
            <CardDescription>Which Chromium runs, and whether you can see it.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <SelectField
                label="Channel"
                value={draft.browserChannel}
                options={BROWSER_CHANNELS.map((value) => ({ value, label: value }))}
                onValueChange={(value) =>
                  set('browserChannel', value as Settings['browserChannel'])
                }
              />
              <TextField
                label="Executable path"
                value={draft.browserExecutablePath ?? ''}
                placeholder="Empty uses the bundled Chromium"
                hint={
                  'Brave on Windows: C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe'
                }
                onChange={(event) =>
                  set(
                    'browserExecutablePath',
                    event.target.value === '' ? null : event.target.value,
                  )
                }
              />
            </div>
            <CheckboxField
              label="Run headless"
              hint="A visible window is usually wanted: captchas and checkpoints are solved by hand, inside the profile."
              checked={draft.headless}
              onCheckedChange={(headless) => set('headless', headless)}
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Anti-spam delays</CardTitle>
            <CardDescription>
              Every share, join and comment waits a random time inside its range, so no two runs
              share a rhythm. These protect the accounts; do not set them to zero.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            {DELAY_RANGES.map((range) => (
              <div key={range.min} className="grid gap-3 sm:grid-cols-2">
                <TextField
                  label={`${range.label}, from (seconds)`}
                  type="number"
                  min={0}
                  step="any"
                  value={seconds(draft[range.min] as number)}
                  onChange={(event) =>
                    set(
                      range.min,
                      fromSeconds(event.target.value, draft[range.min] as number) as never,
                    )
                  }
                />
                <TextField
                  label={`${range.label}, to (seconds)`}
                  type="number"
                  min={0}
                  step="any"
                  value={seconds(draft[range.max] as number)}
                  onChange={(event) =>
                    set(
                      range.max,
                      fromSeconds(event.target.value, draft[range.max] as number) as never,
                    )
                  }
                />
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Queue</CardTitle>
            <CardDescription>
              How much runs at once, and what happens when it fails or waits.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <TextField
              label="Global concurrency"
              type="number"
              min={1}
              max={64}
              value={String(draft.globalConcurrency)}
              hint="Jobs that may run at the same time, across all accounts."
              onChange={(event) =>
                set('globalConcurrency', number(event.target.value, draft.globalConcurrency))
              }
            />
            <TextField
              label="Default retries"
              type="number"
              min={0}
              max={10}
              value={String(draft.defaultMaxRetries)}
              onChange={(event) =>
                set('defaultMaxRetries', number(event.target.value, draft.defaultMaxRetries))
              }
            />
            <TextField
              label="Step timeout (seconds)"
              type="number"
              min={1}
              step="any"
              value={seconds(draft.defaultTimeoutMs)}
              onChange={(event) =>
                set('defaultTimeoutMs', fromSeconds(event.target.value, draft.defaultTimeoutMs))
              }
            />
            <TextField
              label="Retry backoff (seconds)"
              type="number"
              min={1}
              step="any"
              value={seconds(draft.retryBackoffMs)}
              hint="The first wait. Later attempts double it, with jitter."
              onChange={(event) =>
                set('retryBackoffMs', fromSeconds(event.target.value, draft.retryBackoffMs))
              }
            />
            <TextField
              label="Wait for a person (seconds)"
              type="number"
              min={10}
              step="any"
              value={seconds(draft.operatorInputTimeoutMs)}
              hint="How long a job holds on a captcha or checkpoint before it gives up."
              onChange={(event) =>
                set(
                  'operatorInputTimeoutMs',
                  fromSeconds(event.target.value, draft.operatorInputTimeoutMs),
                )
              }
            />
            <TextField
              label="Profile lock TTL (seconds)"
              type="number"
              min={30}
              step="any"
              value={seconds(draft.profileLockTtlMs)}
              hint="How long a lock survives before it counts as abandoned."
              onChange={(event) =>
                set('profileLockTtlMs', fromSeconds(event.target.value, draft.profileLockTtlMs))
              }
            />
            <TextField
              label="Stale job timeout (seconds)"
              type="number"
              min={60}
              step="any"
              value={seconds(draft.staleJobTimeoutMs)}
              onChange={(event) =>
                set('staleJobTimeoutMs', fromSeconds(event.target.value, draft.staleJobTimeoutMs))
              }
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Storage</CardTitle>
            <CardDescription>
              Set in the environment, read here. The browser can see where things live but never
              move them.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {paths.isSuccess && (
              <dl className="grid gap-3 text-sm sm:grid-cols-2">
                <Path label="Database" value={paths.data.databaseFile} />
                <Path label="Browser profiles" value={paths.data.profileDir} />
                <Path label="Uploads" value={paths.data.uploadDir} />
                <Path label="Exports" value={paths.data.exportDir} />
                <Path label="Logs" value={paths.data.logDir} />
              </dl>
            )}
          </CardContent>
        </Card>

        {problems.length > 0 && <ErrorNotice error={new Error(problems.join('; '))} />}
        {update.error !== null && <ErrorNotice error={update.error} />}

        <div className="flex items-center justify-end gap-3">
          {dirty && <span className="text-sm text-muted-foreground">Unsaved changes</span>}
          <Button type="submit" disabled={update.isPending}>
            Save settings
          </Button>
        </div>
      </form>
    </div>
  );
};

const Path = ({ label, value }: { label: string; value: string }): ReactElement => (
  <div className="grid gap-0.5">
    <dt className="text-xs text-muted-foreground">{label}</dt>
    <dd className="font-mono text-xs break-all">{value}</dd>
  </div>
);
