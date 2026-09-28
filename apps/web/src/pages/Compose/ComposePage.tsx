import { useMemo, useState, type ChangeEvent, type FormEvent, type ReactElement } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AutomationActionSchema,
  POST_AUDIENCES,
  REACTION_TYPES,
  type AutomationActionInput,
  type JobType,
  type MediaRef,
} from '@fb/shared';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { ErrorNotice, InfoNotice } from '../../components/ui/Feedback';
import { PageHeader } from '../../components/ui/PageHeader';
import { SelectField, TextAreaField, TextField } from '../../components/forms/Field';
import { useAccounts } from '../../features/accounts/hooks';
import { useCreateJobs } from '../../features/queue/hooks';
import { uploadMedia } from '../../api/system';
import { bytes, humanise } from '../../lib/format';
import './ComposePage.css';

const ACTION_TYPES: ReadonlyArray<{ value: JobType; label: string }> = [
  { value: 'create_post', label: 'Create post' },
  { value: 'upload_media', label: 'Upload media' },
  { value: 'comment', label: 'Comment' },
  { value: 'react_to_post', label: 'React to post' },
  { value: 'send_message', label: 'Send message' },
];

interface FormState {
  type: JobType;
  text: string;
  postUrl: string;
  targetUrl: string;
  threadId: string;
  reaction: string;
  audience: string;
  caption: string;
  priority: string;
  scheduledFor: string;
}

const initialForm: FormState = {
  type: 'create_post',
  text: '',
  postUrl: '',
  targetUrl: '',
  threadId: '',
  reaction: 'like',
  audience: 'friends',
  caption: '',
  priority: '0',
  scheduledFor: '',
};

/**
 * Builds the action from the form. The shape is validated against the same
 * schema the server uses, so an invalid combination is caught here rather than
 * becoming a failed job later.
 */
const buildAction = (form: FormState, media: MediaRef[]): AutomationActionInput => {
  switch (form.type) {
    case 'create_post':
      return {
        type: 'create_post',
        text: form.text,
        media,
        audience: form.audience as (typeof POST_AUDIENCES)[number],
      };
    case 'upload_media':
      return {
        type: 'upload_media',
        targetUrl: form.targetUrl,
        media,
        ...(form.caption === '' ? {} : { caption: form.caption }),
      };
    case 'comment':
      return { type: 'comment', postUrl: form.postUrl, text: form.text };
    case 'react_to_post':
      return {
        type: 'react_to_post',
        postUrl: form.postUrl,
        reaction: form.reaction as (typeof REACTION_TYPES)[number],
      };
    case 'send_message':
      return { type: 'send_message', threadId: form.threadId, text: form.text, media };
  }
};

export const ComposePage = (): ReactElement => {
  const navigate = useNavigate();
  const accounts = useAccounts({ limit: 200, enabled: true });
  const createJobs = useCreateJobs();

  const [form, setForm] = useState<FormState>(initialForm);
  const [selected, setSelected] = useState<string[]>([]);
  const [media, setMedia] = useState<MediaRef[]>([]);
  const [uploading, setUploading] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]): void =>
    setForm((state) => ({ ...state, [key]: value }));

  const usesMedia = form.type !== 'comment' && form.type !== 'react_to_post';
  const usesText =
    form.type === 'create_post' || form.type === 'comment' || form.type === 'send_message';

  const availableAccounts = accounts.data?.items ?? [];
  const allSelected = selected.length > 0 && selected.length === availableAccounts.length;

  const toggleAccount = (id: string): void =>
    setSelected((state) =>
      state.includes(id) ? state.filter((item) => item !== id) : [...state, id],
    );

  const upload = async (event: ChangeEvent<HTMLInputElement>): Promise<void> => {
    const files = [...(event.target.files ?? [])];
    if (files.length === 0) return;

    setUploading(true);
    setProblem(null);
    try {
      // Uploaded one at a time: the server accepts a single file per request,
      // and a partial failure then names the file that failed.
      const uploaded: MediaRef[] = [];
      for (const file of files) uploaded.push(await uploadMedia(file));
      setMedia((state) => [...state, ...uploaded]);
    } catch (error) {
      setProblem(error instanceof Error ? error.message : 'The upload failed');
    } finally {
      setUploading(false);
      event.target.value = '';
    }
  };

  const submit = (event: FormEvent): void => {
    event.preventDefault();
    setProblem(null);

    if (selected.length === 0) {
      setProblem('Choose at least one account');
      return;
    }

    const parsed = AutomationActionSchema.safeParse(buildAction(form, media));
    if (!parsed.success) {
      setProblem(parsed.error.issues[0]?.message ?? 'Check the action details');
      return;
    }

    createJobs.mutate(
      {
        accountIds: selected,
        action: parsed.data,
        priority: Number(form.priority),
        ...(form.scheduledFor === ''
          ? {}
          : { scheduledFor: new Date(form.scheduledFor).toISOString() }),
      },
      {
        onSuccess: () => {
          setForm(initialForm);
          setMedia([]);
          setSelected([]);
          void navigate('/queue');
        },
      },
    );
  };

  const summary = useMemo(
    () =>
      selected.length === 0
        ? 'No accounts chosen'
        : `${selected.length} job${selected.length === 1 ? '' : 's'} will be created`,
    [selected.length],
  );

  return (
    <div className="page">
      <PageHeader
        title="Compose"
        description="Create work for one account or many. The queue runs it; this page never drives a browser."
      />

      <form className="compose" onSubmit={submit}>
        <Card title="Action">
          <div className="stack">
            <SelectField
              label="Type"
              value={form.type}
              options={ACTION_TYPES}
              onChange={(event) => set('type', event.target.value as JobType)}
            />

            {form.type === 'create_post' && (
              <SelectField
                label="Audience"
                value={form.audience}
                options={POST_AUDIENCES.map((value) => ({ value, label: humanise(value) }))}
                onChange={(event) => set('audience', event.target.value)}
              />
            )}

            {(form.type === 'comment' || form.type === 'react_to_post') && (
              <TextField
                label="Post URL"
                value={form.postUrl}
                placeholder="https://www.facebook.com/…"
                onChange={(event) => set('postUrl', event.target.value)}
              />
            )}

            {form.type === 'react_to_post' && (
              <SelectField
                label="Reaction"
                value={form.reaction}
                options={REACTION_TYPES.map((value) => ({ value, label: humanise(value) }))}
                onChange={(event) => set('reaction', event.target.value)}
              />
            )}

            {form.type === 'upload_media' && (
              <>
                <TextField
                  label="Destination URL"
                  value={form.targetUrl}
                  placeholder="https://www.facebook.com/…"
                  onChange={(event) => set('targetUrl', event.target.value)}
                />
                <TextField
                  label="Caption"
                  value={form.caption}
                  placeholder="Optional"
                  onChange={(event) => set('caption', event.target.value)}
                />
              </>
            )}

            {form.type === 'send_message' && (
              <TextField
                label="Thread or profile id"
                value={form.threadId}
                onChange={(event) => set('threadId', event.target.value)}
              />
            )}

            {usesText && (
              <TextAreaField
                label={form.type === 'send_message' ? 'Message' : 'Text'}
                value={form.text}
                placeholder="What should this account say?"
                onChange={(event) => set('text', event.target.value)}
              />
            )}

            {usesMedia && (
              <div className="compose__media">
                <label className="field__label" htmlFor="compose-media">
                  Media
                </label>
                <input
                  id="compose-media"
                  type="file"
                  multiple
                  accept="image/jpeg,image/png,image/gif,image/webp,video/mp4,video/quicktime"
                  onChange={(event) => void upload(event)}
                  disabled={uploading}
                />
                {media.length > 0 && (
                  <ul className="compose__files">
                    {media.map((file) => (
                      <li key={file.id}>
                        <span>{file.fileName}</span>
                        <span className="muted">{bytes(file.sizeBytes)}</span>
                        <button
                          type="button"
                          onClick={() =>
                            setMedia((state) => state.filter((item) => item.id !== file.id))
                          }
                          aria-label={`Remove ${file.fileName}`}
                        >
                          ×
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        </Card>

        <Card title="Scheduling">
          <div className="row">
            <TextField
              label="Priority"
              type="number"
              min={-100}
              max={100}
              value={form.priority}
              hint="Higher runs first."
              onChange={(event) => set('priority', event.target.value)}
            />
            <TextField
              label="Run after"
              type="datetime-local"
              value={form.scheduledFor}
              hint="Leave empty to run as soon as a worker is free."
              onChange={(event) => set('scheduledFor', event.target.value)}
            />
          </div>
        </Card>

        <Card
          title="Accounts"
          actions={
            <Button
              size="sm"
              variant="ghost"
              onClick={() =>
                setSelected(allSelected ? [] : availableAccounts.map((account) => account.id))
              }
            >
              {allSelected ? 'Clear' : 'Select all'}
            </Button>
          }
        >
          {availableAccounts.length === 0 ? (
            <InfoNotice>
              No enabled accounts. Add one on the Accounts page before composing work.
            </InfoNotice>
          ) : (
            <ul className="compose__accounts">
              {availableAccounts.map((account) => (
                <li key={account.id}>
                  <label className="compose__account">
                    <input
                      type="checkbox"
                      checked={selected.includes(account.id)}
                      onChange={() => toggleAccount(account.id)}
                    />
                    <span>{account.displayName}</span>
                    <span className="muted">{account.status}</span>
                  </label>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {problem !== null && <ErrorNotice error={new Error(problem)} />}
        {createJobs.error !== null && <ErrorNotice error={createJobs.error} />}

        <div className="compose__submit">
          <span className="muted">{summary}</span>
          <Button type="submit" variant="primary" loading={createJobs.isPending || uploading}>
            Queue work
          </Button>
        </div>
      </form>
    </div>
  );
};
