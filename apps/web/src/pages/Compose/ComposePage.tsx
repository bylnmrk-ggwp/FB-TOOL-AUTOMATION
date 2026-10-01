import { useMemo, useState, type ChangeEvent, type FormEvent, type ReactElement } from 'react';
import { useNavigate } from 'react-router-dom';
import { Paperclip, X } from 'lucide-react';
import { toast } from 'sonner';
import {
  AutomationActionSchema,
  POST_AUDIENCES,
  REACTION_TYPES,
  type AutomationActionInput,
  type JobType,
  type MediaRef,
  type ReactionType,
} from '@fb/shared';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ErrorNotice, InfoNotice } from '@/components/common/Feedback';
import { PageHeader } from '@/components/common/PageHeader';
import { AccountStatusDot, LoginStatusDot } from '@/components/common/StatusDot';
import {
  CheckboxField,
  NativeSelect,
  SelectField,
  TextAreaField,
  TextField,
} from '@/components/forms/Field';
import { cn } from '@/lib/utils';
import { useAllAccounts } from '../../features/accounts/hooks';
import { LOGIN_OPTIONS, STATUS_OPTIONS } from '../../features/accounts/options';
import { useGroupSummaries } from '../../features/groups/hooks';
import { useCreateJobs, useJoinGroups, useShareToGroups } from '../../features/queue/hooks';
import { uploadMedia } from '../../api/system';
import { bytes, humanise } from '../../lib/format';

type ComposeKind = JobType | 'share_to_groups';

const ACTION_TYPES: ReadonlyArray<{ value: ComposeKind; label: string; help: string }> = [
  {
    value: 'share_to_groups',
    label: 'Share a post to groups',
    help: 'One job per account and group.',
  },
  { value: 'share_post', label: 'Share a post to the timeline or story', help: '' },
  { value: 'create_post', label: 'Post text and photos', help: '' },
  { value: 'join_group', label: 'Join groups', help: 'One job per account and group URL.' },
  { value: 'comment', label: 'Comment on a post', help: '' },
  { value: 'react_to_post', label: 'React to a post', help: '' },
  { value: 'send_message', label: 'Send a message', help: '' },
  {
    value: 'watch_live',
    label: 'Watch a live video',
    help: 'Keeps the video playing in each browser.',
  },
  { value: 'upload_media', label: 'Upload media to a page or group', help: '' },
  { value: 'login', label: 'Log in with stored credentials', help: '' },
  { value: 'check_login', label: 'Check the login', help: '' },
  { value: 'fetch_groups', label: 'Fetch the group list', help: '' },
  { value: 'accept_friend_requests', label: 'Accept friend requests', help: '' },
  { value: 'add_friends', label: 'Add friends from suggestions', help: '' },
  {
    value: 'auto_setup_profile',
    label: 'Auto-set up the profile',
    help: 'Requests, friends, picture, bio.',
  },
];

const REACTION_OPTIONS = [
  { value: '', label: 'No reaction' },
  ...REACTION_TYPES.map((value) => ({ value, label: humanise(value) })),
];

interface FormState {
  kind: ComposeKind;
  text: string;
  comments: string;
  postUrl: string;
  targetUrl: string;
  threadId: string;
  groupUrls: string;
  reaction: string;
  audience: string;
  caption: string;
  targets: { timeline: boolean; story: boolean };
  shareToTimeline: boolean;
  skipDone: boolean;
  minutes: string;
  untilEnd: boolean;
  targetFriends: string;
  bio: string;
  connectFriends: boolean;
  waitForOperator: boolean;
  priority: string;
  scheduledFor: string;
}

const initialForm: FormState = {
  kind: 'share_to_groups',
  text: '',
  comments: '',
  postUrl: '',
  targetUrl: '',
  threadId: '',
  groupUrls: '',
  reaction: '',
  audience: 'friends',
  caption: '',
  targets: { timeline: true, story: false },
  shareToTimeline: false,
  skipDone: true,
  minutes: '30',
  untilEnd: false,
  targetFriends: '50',
  bio: '',
  connectFriends: true,
  waitForOperator: true,
  priority: '0',
  scheduledFor: '',
};

const lines = (value: string): string[] =>
  value
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line !== '');

const reactionOf = (value: string): ReactionType | null =>
  value === '' ? null : (value as ReactionType);

/**
 * Builds the single-action payload for every kind that maps to one job per
 * account. Share-to-groups and join are fan-outs and go through their own
 * endpoints instead.
 */
const buildAction = (form: FormState, media: MediaRef[]): AutomationActionInput | null => {
  switch (form.kind) {
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
        reaction: (form.reaction || 'like') as ReactionType,
      };
    case 'send_message':
      return { type: 'send_message', threadId: form.threadId, text: form.text, media };
    case 'share_post':
      return {
        type: 'share_post',
        postUrl: form.postUrl,
        targets: [
          ...(form.targets.timeline ? ['timeline' as const] : []),
          ...(form.targets.story ? ['story' as const] : []),
        ],
        reaction: reactionOf(form.reaction),
        comments: lines(form.comments),
      };
    case 'watch_live':
      return {
        type: 'watch_live',
        url: form.postUrl,
        minutes: form.untilEnd ? null : Number(form.minutes),
      };
    case 'login':
      return { type: 'login', waitForOperator: form.waitForOperator };
    case 'check_login':
      return { type: 'check_login' };
    case 'fetch_groups':
      return { type: 'fetch_groups' };
    case 'accept_friend_requests':
      return { type: 'accept_friend_requests', max: 100 };
    case 'add_friends':
      return { type: 'add_friends', target: Number(form.targetFriends) || 50 };
    case 'auto_setup_profile':
      return {
        type: 'auto_setup_profile',
        targetFriends: Number(form.targetFriends) || 50,
        connectFriends: form.connectFriends,
        bio: form.bio.trim() === '' ? null : form.bio.trim(),
        profilePicture: media[0] ?? null,
      };
    case 'share_to_groups':
    case 'share_to_group':
    case 'join_group':
      return null;
  }
};

export const ComposePage = (): ReactElement => {
  const navigate = useNavigate();
  const accounts = useAllAccounts({ enabled: true });
  const groupSummaries = useGroupSummaries();
  const createJobs = useCreateJobs();
  const shareToGroups = useShareToGroups();
  const joinGroups = useJoinGroups();

  const [form, setForm] = useState<FormState>(initialForm);
  const [selected, setSelected] = useState<string[]>([]);
  const [accountSearch, setAccountSearch] = useState('');
  const [accountLogin, setAccountLogin] = useState('');
  const [accountStatus, setAccountStatus] = useState('');
  const [pickedGroups, setPickedGroups] = useState<Set<string>>(new Set());
  const [groupSearch, setGroupSearch] = useState('');
  const [media, setMedia] = useState<MediaRef[]>([]);
  const [uploading, setUploading] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]): void =>
    setForm((state) => ({ ...state, [key]: value }));

  const kind = form.kind;
  const usesPostUrl = [
    'share_to_groups',
    'share_post',
    'comment',
    'react_to_post',
    'watch_live',
  ].includes(kind);
  const usesMedia = ['create_post', 'upload_media', 'send_message', 'auto_setup_profile'].includes(
    kind,
  );
  const usesComments = kind === 'share_to_groups' || kind === 'share_post';
  const usesReaction = usesComments || kind === 'react_to_post';
  const pending =
    createJobs.isPending || shareToGroups.isPending || joinGroups.isPending || uploading;

  const availableAccounts = useMemo(() => {
    const needle = accountSearch.trim().toLowerCase();
    return (accounts.data ?? []).filter(
      (account) =>
        (accountLogin === '' || account.loginStatus === accountLogin) &&
        (accountStatus === '' || account.status === accountStatus) &&
        (needle === '' ||
          account.displayName.toLowerCase().includes(needle) ||
          (account.facebookName ?? '').toLowerCase().includes(needle) ||
          (account.username ?? '').toLowerCase().includes(needle)),
    );
  }, [accounts.data, accountSearch, accountLogin, accountStatus]);
  const accountsFiltered =
    accountSearch.trim() !== '' || accountLogin !== '' || accountStatus !== '';
  const allSelected =
    availableAccounts.length > 0 &&
    availableAccounts.every((account) => selected.includes(account.id));

  const groups = useMemo(() => {
    const needle = groupSearch.trim().toLowerCase();
    return (groupSummaries.data ?? []).filter(
      (group) => needle === '' || group.name.toLowerCase().includes(needle),
    );
  }, [groupSummaries.data, groupSearch]);

  const toggleAccount = (id: string): void =>
    setSelected((state) =>
      state.includes(id) ? state.filter((item) => item !== id) : [...state, id],
    );

  const toggleGroup = (url: string): void =>
    setPickedGroups((state) => {
      const next = new Set(state);
      if (next.has(url)) next.delete(url);
      else next.add(url);
      return next;
    });

  const upload = async (event: ChangeEvent<HTMLInputElement>): Promise<void> => {
    const files = [...(event.target.files ?? [])];
    if (files.length === 0) return;
    setUploading(true);
    setProblem(null);
    try {
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

  const done = (count: number): void => {
    toast.success(`Queued ${count} job${count === 1 ? '' : 's'}`);
    setForm(initialForm);
    setMedia([]);
    setSelected([]);
    setPickedGroups(new Set());
    void navigate('/queue');
  };

  const submit = (event: FormEvent): void => {
    event.preventDefault();
    setProblem(null);

    if (selected.length === 0) {
      setProblem('Choose at least one account');
      return;
    }
    const priority = Number(form.priority) || 0;
    const onError = (error: Error): void => setProblem(error.message);

    if (kind === 'share_to_groups') {
      const chosenGroups = (groupSummaries.data ?? []).filter((group) =>
        pickedGroups.has(group.url),
      );
      if (form.postUrl.trim() === '') return setProblem('Enter the URL of the post to share');
      if (chosenGroups.length === 0) return setProblem('Pick at least one group');
      shareToGroups.mutate(
        {
          accountIds: selected,
          postUrl: form.postUrl.trim(),
          groups: chosenGroups.map((group) => ({ name: group.name, url: group.url })),
          comments: lines(form.comments),
          reaction: reactionOf(form.reaction),
          shareToTimeline: form.shareToTimeline,
          skipDone: form.skipDone,
          priority,
        },
        { onError, onSuccess: (result) => done(result.jobs.length) },
      );
      return;
    }

    if (kind === 'join_group') {
      const urls = lines(form.groupUrls).filter((url) => url.startsWith('http'));
      if (urls.length === 0) return setProblem('Enter at least one group URL');
      joinGroups.mutate(
        { accountIds: selected, groupUrls: urls, skipDone: form.skipDone, priority },
        { onError, onSuccess: (result) => done(result.jobs.length) },
      );
      return;
    }

    const action = buildAction(form, media);
    if (action === null) return;
    const parsed = AutomationActionSchema.safeParse(action);
    if (!parsed.success) {
      setProblem(parsed.error.issues[0]?.message ?? 'Check the action details');
      return;
    }

    createJobs.mutate(
      {
        accountIds: selected,
        action: parsed.data,
        priority,
        ...(form.scheduledFor === ''
          ? {}
          : { scheduledFor: new Date(form.scheduledFor).toISOString() }),
      },
      { onError, onSuccess: (result) => done(result.jobs.length) },
    );
  };

  const summary = (() => {
    if (selected.length === 0) return 'No accounts chosen';
    if (kind === 'share_to_groups')
      return `${selected.length * pickedGroups.size} jobs (accounts × groups)`;
    if (kind === 'join_group')
      return `${selected.length * lines(form.groupUrls).length} jobs (accounts × URLs)`;
    return `${selected.length} job${selected.length === 1 ? '' : 's'} will be created`;
  })();

  const current = ACTION_TYPES.find((option) => option.value === kind);

  return (
    <div className="grid gap-6">
      <PageHeader
        title="Compose"
        description="Queue one action for one account or many. The queue runs it — this page never drives a browser."
      />

      <form className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_380px]" onSubmit={submit}>
        <div className="grid min-w-0 content-start gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Action</CardTitle>
              <CardDescription>
                {current?.help === '' ? 'What each chosen account should do.' : current?.help}
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4">
              <SelectField
                label="Type"
                value={kind}
                options={ACTION_TYPES.map((option) => ({
                  value: option.value,
                  label: option.label,
                }))}
                onValueChange={(value) => set('kind', value as ComposeKind)}
              />

              {usesPostUrl && (
                <TextField
                  label={kind === 'watch_live' ? 'Live video URL' : 'Post URL'}
                  value={form.postUrl}
                  placeholder="https://www.facebook.com/…"
                  onChange={(event) => set('postUrl', event.target.value)}
                />
              )}

              {kind === 'share_post' && (
                <div className="grid gap-2">
                  <Label>Share to</Label>
                  <CheckboxField
                    label="Timeline"
                    checked={form.targets.timeline}
                    onCheckedChange={(v) => set('targets', { ...form.targets, timeline: v })}
                  />
                  <CheckboxField
                    label="Story"
                    checked={form.targets.story}
                    onCheckedChange={(v) => set('targets', { ...form.targets, story: v })}
                  />
                </div>
              )}

              {kind === 'share_to_groups' && (
                <>
                  <div className="grid gap-2">
                    <div className="flex items-center justify-between gap-2">
                      <Label>Groups ({pickedGroups.size} picked)</Label>
                      <div className="flex gap-1">
                        <Button
                          type="button"
                          size="xs"
                          variant="ghost"
                          onClick={() => setPickedGroups(new Set(groups.map((group) => group.url)))}
                        >
                          All shown
                        </Button>
                        <Button
                          type="button"
                          size="xs"
                          variant="ghost"
                          onClick={() => setPickedGroups(new Set())}
                        >
                          None
                        </Button>
                      </div>
                    </div>
                    <TextField
                      label="Filter groups"
                      value={groupSearch}
                      placeholder="Type to filter"
                      onChange={(event) => setGroupSearch(event.target.value)}
                    />
                    {(groupSummaries.data ?? []).length === 0 ? (
                      <InfoNotice>
                        No groups known yet. Fetch them on the Groups page first.
                      </InfoNotice>
                    ) : (
                      <ul className="grid max-h-56 gap-1 overflow-y-auto rounded-md border p-1">
                        {groups.map((group) => (
                          <li key={group.url}>
                            <label className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-accent/60">
                              <Checkbox
                                checked={pickedGroups.has(group.url)}
                                onCheckedChange={() => toggleGroup(group.url)}
                                aria-label={group.name}
                              />
                              <span className="min-w-0 flex-1 truncate">{group.name}</span>
                              <span className="text-xs text-muted-foreground">
                                {group.accountIds.length} acc.
                              </span>
                            </label>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  <CheckboxField
                    label="Share to the timeline and story first"
                    hint="Once per account, before its first group."
                    checked={form.shareToTimeline}
                    onCheckedChange={(v) => set('shareToTimeline', v)}
                  />
                  <CheckboxField
                    label="Skip groups already shared to"
                    checked={form.skipDone}
                    onCheckedChange={(v) => set('skipDone', v)}
                  />
                </>
              )}

              {kind === 'join_group' && (
                <>
                  <TextAreaField
                    label="Group URLs, one per line"
                    value={form.groupUrls}
                    placeholder={
                      'https://www.facebook.com/groups/…\nhttps://www.facebook.com/groups/…'
                    }
                    onChange={(event) => set('groupUrls', event.target.value)}
                  />
                  <CheckboxField
                    label="Skip groups already joined"
                    checked={form.skipDone}
                    onCheckedChange={(v) => set('skipDone', v)}
                  />
                </>
              )}

              {usesReaction && (
                <SelectField
                  label="Reaction"
                  value={form.reaction}
                  options={REACTION_OPTIONS}
                  onValueChange={(value) => set('reaction', value)}
                />
              )}

              {usesComments && (
                <TextAreaField
                  label="Comments, one per line"
                  value={form.comments}
                  hint="Each job picks one line at random, so forty accounts do not leave the same sentence."
                  onChange={(event) => set('comments', event.target.value)}
                />
              )}

              {kind === 'create_post' && (
                <SelectField
                  label="Audience"
                  value={form.audience}
                  options={POST_AUDIENCES.map((value) => ({ value, label: humanise(value) }))}
                  onValueChange={(value) => set('audience', value)}
                />
              )}

              {kind === 'upload_media' && (
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

              {kind === 'send_message' && (
                <TextField
                  label="Thread or profile id"
                  value={form.threadId}
                  onChange={(event) => set('threadId', event.target.value)}
                />
              )}

              {(kind === 'create_post' || kind === 'comment' || kind === 'send_message') && (
                <TextAreaField
                  label={kind === 'send_message' ? 'Message' : 'Text'}
                  value={form.text}
                  placeholder="What should this account say?"
                  onChange={(event) => set('text', event.target.value)}
                />
              )}

              {kind === 'watch_live' && (
                <div className="grid gap-3">
                  <CheckboxField
                    label="Watch until the broadcast ends"
                    checked={form.untilEnd}
                    onCheckedChange={(v) => set('untilEnd', v)}
                  />
                  {!form.untilEnd && (
                    <TextField
                      label="Minutes"
                      type="number"
                      min={1}
                      max={1440}
                      value={form.minutes}
                      onChange={(event) => set('minutes', event.target.value)}
                    />
                  )}
                </div>
              )}

              {kind === 'login' && (
                <CheckboxField
                  label="Wait for me on a captcha or checkpoint"
                  hint="Off: the job fails instead of waiting, and the account is marked with what it needs."
                  checked={form.waitForOperator}
                  onCheckedChange={(v) => set('waitForOperator', v)}
                />
              )}

              {(kind === 'add_friends' || kind === 'auto_setup_profile') && (
                <TextField
                  label="Friend target"
                  type="number"
                  min={0}
                  max={5000}
                  value={form.targetFriends}
                  onChange={(event) => set('targetFriends', event.target.value)}
                />
              )}

              {kind === 'auto_setup_profile' && (
                <>
                  <CheckboxField
                    label="Add friends from suggestions"
                    hint="Off when the accounts will befriend each other instead."
                    checked={form.connectFriends}
                    onCheckedChange={(v) => set('connectFriends', v)}
                  />
                  <TextField
                    label="Bio"
                    value={form.bio}
                    placeholder="Optional"
                    onChange={(event) => set('bio', event.target.value)}
                  />
                </>
              )}

              {usesMedia && (
                <div className="grid gap-2">
                  <Label htmlFor="compose-media">
                    {kind === 'auto_setup_profile' ? 'Profile picture' : 'Media'}
                  </Label>
                  <label
                    htmlFor="compose-media"
                    className={cn(
                      'flex cursor-pointer items-center gap-2 rounded-md border border-dashed px-3 py-3 text-sm text-muted-foreground transition-colors hover:border-ring hover:text-foreground',
                      uploading && 'pointer-events-none opacity-60',
                    )}
                  >
                    <Paperclip className="size-4" />
                    {uploading
                      ? 'Uploading…'
                      : kind === 'auto_setup_profile'
                        ? 'Attach a picture (at least 180×180)'
                        : 'Attach images or video'}
                  </label>
                  <input
                    id="compose-media"
                    type="file"
                    multiple={kind !== 'auto_setup_profile'}
                    className="sr-only"
                    accept="image/jpeg,image/png,image/gif,image/webp,video/mp4,video/quicktime"
                    onChange={(event) => void upload(event)}
                    disabled={uploading}
                  />
                  {media.length > 0 && (
                    <ul className="grid gap-1.5">
                      {media.map((file) => (
                        <li
                          key={file.id}
                          className="grid grid-cols-[1fr_auto_auto] items-center gap-3 rounded-md border px-3 py-1.5 text-sm"
                        >
                          <span className="truncate">{file.fileName}</span>
                          <span className="text-xs text-muted-foreground">
                            {bytes(file.sizeBytes)}
                          </span>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon-xs"
                            aria-label={`Remove ${file.fileName}`}
                            onClick={() =>
                              setMedia((state) => state.filter((item) => item.id !== file.id))
                            }
                          >
                            <X />
                          </Button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Scheduling</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
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
            </CardContent>
          </Card>
        </div>

        <div className="grid min-w-0 content-start gap-4">
          <Card className="min-w-0 gap-0 py-0">
            <CardHeader className="flex flex-row items-center justify-between border-b px-5 py-3">
              <CardTitle className="text-sm">Accounts</CardTitle>
              {availableAccounts.length > 0 && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    setSelected((state) => {
                      const shown = availableAccounts.map((account) => account.id);
                      if (allSelected) return state.filter((id) => !shown.includes(id));
                      return [...new Set([...state, ...shown])];
                    })
                  }
                >
                  {allSelected ? 'Clear shown' : `Select all ${availableAccounts.length}`}
                </Button>
              )}
            </CardHeader>
            <CardContent className="px-0 py-0">
              {(accounts.data?.length ?? 0) > 8 && (
                <div className="grid gap-2 border-b px-3 py-2">
                  <Input
                    aria-label="Filter accounts"
                    placeholder="Filter by name or username"
                    value={accountSearch}
                    onChange={(event) => setAccountSearch(event.target.value)}
                  />
                  <div className="grid grid-cols-2 gap-2">
                    <NativeSelect
                      aria-label="Login state"
                      value={accountLogin}
                      options={LOGIN_OPTIONS}
                      onValueChange={setAccountLogin}
                    />
                    <NativeSelect
                      aria-label="Browser state"
                      value={accountStatus}
                      options={STATUS_OPTIONS}
                      onValueChange={setAccountStatus}
                    />
                  </div>
                </div>
              )}
              {availableAccounts.length === 0 ? (
                <div className="p-4">
                  <InfoNotice>
                    {accountsFiltered
                      ? 'No account matches that filter.'
                      : 'No enabled accounts. Import the roster or add one on the Accounts page.'}
                  </InfoNotice>
                </div>
              ) : (
                <ul className="max-h-[480px] divide-y overflow-y-auto">
                  {availableAccounts.map((account) => {
                    const id = `account-${account.id}`;
                    return (
                      <li key={account.id}>
                        <label
                          htmlFor={id}
                          className="flex cursor-pointer items-center gap-3 px-4 py-2 text-sm hover:bg-accent/60"
                        >
                          <Checkbox
                            id={id}
                            checked={selected.includes(account.id)}
                            onCheckedChange={() => toggleAccount(account.id)}
                            aria-label={account.displayName}
                          />
                          <span className="min-w-0 flex-1 truncate">
                            {account.facebookName ?? account.displayName}
                          </span>
                          <span className="hidden shrink-0 sm:block">
                            <LoginStatusDot status={account.loginStatus} />
                          </span>
                          <AccountStatusDot status={account.status} />
                        </label>
                      </li>
                    );
                  })}
                </ul>
              )}
            </CardContent>
          </Card>

          {problem !== null && <ErrorNotice error={new Error(problem)} />}

          <div className="flex items-center justify-between gap-3">
            <span className="text-sm text-muted-foreground">{summary}</span>
            <Button type="submit" disabled={pending}>
              Queue work
            </Button>
          </div>
        </div>
      </form>
    </div>
  );
};
