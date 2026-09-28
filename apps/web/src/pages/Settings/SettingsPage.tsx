import { useEffect, useState, type FormEvent, type ReactElement } from 'react';
import { BROWSER_CHANNELS, SettingsSchema, validateSettings, type Settings } from '@fb/shared';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { ErrorNotice, InfoNotice, Loading } from '../../components/ui/Feedback';
import { PageHeader } from '../../components/ui/PageHeader';
import { CheckboxField, SelectField, TextField } from '../../components/forms/Field';
import { useSettings, useSystemPaths, useUpdateSettings } from '../../features/settings/hooks';
import './SettingsPage.css';

export const SettingsPage = (): ReactElement => {
  const settings = useSettings();
  const paths = useSystemPaths();
  const update = useUpdateSettings();

  const [draft, setDraft] = useState<Settings | null>(null);
  const [problems, setProblems] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);

  // The form starts from what the server has, and only the fields a person
  // actually changed are sent back.
  useEffect(() => {
    if (settings.data !== undefined && draft === null) setDraft(settings.data);
  }, [settings.data, draft]);

  if (settings.isPending || draft === null) return <Loading label="Loading settings…" />;
  if (settings.isError) return <ErrorNotice error={settings.error} />;

  const set = <K extends keyof Settings>(key: K, value: Settings[K]): void => {
    setSaved(false);
    setDraft((state) => (state === null ? state : { ...state, [key]: value }));
  };

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
        setSaved(true);
      },
    });
  };

  return (
    <div className="page">
      <PageHeader
        title="Settings"
        description="Applied to the next browser and the next queue pass — no restart needed."
      />

      <form className="settings" onSubmit={submit}>
        <Card title="Browser">
          <div className="settings__grid">
            <SelectField
              label="Channel"
              value={draft.browserChannel}
              options={BROWSER_CHANNELS.map((value) => ({ value, label: value }))}
              onChange={(event) =>
                set('browserChannel', event.target.value as Settings['browserChannel'])
              }
            />
            <TextField
              label="Executable path"
              value={draft.browserExecutablePath ?? ''}
              placeholder="Leave empty to use the bundled Chromium"
              hint="Point this at Brave or another Chromium build to use it instead."
              onChange={(event) =>
                set('browserExecutablePath', event.target.value === '' ? null : event.target.value)
              }
            />
          </div>

          <CheckboxField
            label="Run headless"
            hint="A visible window is usually wanted: signing in happens by hand, inside the profile."
            checked={draft.headless}
            onChange={(event) => set('headless', event.target.checked)}
          />
        </Card>

        <Card title="Queue">
          <div className="settings__grid">
            <TextField
              label="Global concurrency"
              type="number"
              min={1}
              max={32}
              value={String(draft.globalConcurrency)}
              hint="How many jobs may run at once, across all accounts."
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
              label="Default timeout (ms)"
              type="number"
              min={1000}
              step={500}
              value={String(draft.defaultTimeoutMs)}
              onChange={(event) =>
                set('defaultTimeoutMs', number(event.target.value, draft.defaultTimeoutMs))
              }
            />
            <TextField
              label="Retry backoff (ms)"
              type="number"
              min={1000}
              step={500}
              value={String(draft.retryBackoffMs)}
              hint="The first wait; later attempts double it, with jitter."
              onChange={(event) =>
                set('retryBackoffMs', number(event.target.value, draft.retryBackoffMs))
              }
            />
          </div>
        </Card>

        <Card title="Pacing and locks">
          <div className="settings__grid">
            <TextField
              label="Minimum step delay (ms)"
              type="number"
              min={0}
              value={String(draft.minActionDelayMs)}
              onChange={(event) =>
                set('minActionDelayMs', number(event.target.value, draft.minActionDelayMs))
              }
            />
            <TextField
              label="Maximum step delay (ms)"
              type="number"
              min={0}
              value={String(draft.maxActionDelayMs)}
              hint="Each step waits a random time in this range."
              onChange={(event) =>
                set('maxActionDelayMs', number(event.target.value, draft.maxActionDelayMs))
              }
            />
            <TextField
              label="Profile lock TTL (ms)"
              type="number"
              min={30000}
              step={1000}
              value={String(draft.profileLockTtlMs)}
              hint="How long a lock survives before it counts as abandoned."
              onChange={(event) =>
                set('profileLockTtlMs', number(event.target.value, draft.profileLockTtlMs))
              }
            />
            <TextField
              label="Stale job timeout (ms)"
              type="number"
              min={60000}
              step={1000}
              value={String(draft.staleJobTimeoutMs)}
              onChange={(event) =>
                set('staleJobTimeoutMs', number(event.target.value, draft.staleJobTimeoutMs))
              }
            />
          </div>
        </Card>

        <Card title="Storage">
          <InfoNotice>
            Directories come from the environment and cannot be changed from the browser.
          </InfoNotice>
          {paths.isSuccess && (
            <dl className="settings__paths">
              <Path label="Database" value={paths.data.databaseFile} />
              <Path label="Browser profiles" value={paths.data.profileDir} />
              <Path label="Uploads" value={paths.data.uploadDir} />
              <Path label="Exports" value={paths.data.exportDir} />
              <Path label="Logs" value={paths.data.logDir} />
            </dl>
          )}
        </Card>

        {problems.length > 0 && <ErrorNotice error={new Error(problems.join('; '))} />}
        {update.error !== null && <ErrorNotice error={update.error} />}

        <div className="settings__submit">
          {saved && <span className="muted">Saved.</span>}
          <Button type="submit" variant="primary" loading={update.isPending}>
            Save settings
          </Button>
        </div>
      </form>
    </div>
  );
};

const Path = ({ label, value }: { label: string; value: string }): ReactElement => (
  <div>
    <dt>{label}</dt>
    <dd className="mono">{value}</dd>
  </div>
);
