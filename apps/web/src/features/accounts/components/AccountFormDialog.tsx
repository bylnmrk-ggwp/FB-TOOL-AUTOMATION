import { useEffect, useState, type FormEvent, type ReactElement } from 'react';
import { toast } from 'sonner';
import { CreateAccountSchema, type Account } from '@fb/shared';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { ErrorNotice } from '@/components/common/Feedback';
import { CheckboxField, TextField } from '@/components/forms/Field';
import { Modal } from '@/components/dialogs/Modal';
import { useCreateAccount, useUpdateAccount } from '../hooks';

interface AccountFormDialogProps {
  open: boolean;
  /** Null creates a new account; an account edits that one. */
  account: Account | null;
  onClose: () => void;
}

interface FormState {
  name: string;
  displayName: string;
  enabled: boolean;
  username: string;
  password: string;
  gmail: string;
  gmailPassword: string;
  phone: string;
  facebookName: string;
  proxyUrl: string;
}

const emptyForm: FormState = {
  name: '',
  displayName: '',
  enabled: true,
  username: '',
  password: '',
  gmail: '',
  gmailPassword: '',
  phone: '',
  facebookName: '',
  proxyUrl: '',
};

const orNull = (value: string): string | null => (value.trim() === '' ? null : value.trim());

/**
 * One dialog for both creating and editing. The difference is which mutation
 * runs and which fields the server will accept, not a second form.
 *
 * Stored passwords are never shown; the field stays empty and an empty field
 * on save means "keep what is stored".
 */
export const AccountFormDialog = ({
  open,
  account,
  onClose,
}: AccountFormDialogProps): ReactElement => {
  const [form, setForm] = useState<FormState>(emptyForm);
  const [fieldError, setFieldError] = useState<string | null>(null);

  const create = useCreateAccount();
  const update = useUpdateAccount();
  const pending = create.isPending || update.isPending;
  const failure = create.error ?? update.error;

  useEffect(() => {
    if (!open) return;
    setFieldError(null);
    create.reset();
    update.reset();
    setForm(
      account === null
        ? emptyForm
        : {
            name: account.name,
            displayName: account.displayName,
            enabled: account.enabled,
            username: account.username ?? '',
            password: '',
            gmail: account.gmail ?? '',
            gmailPassword: '',
            phone: account.phone ?? '',
            facebookName: account.facebookName ?? '',
            proxyUrl: '',
          },
    );
    // Resetting depends only on which account the dialog was opened for.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, account]);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]): void =>
    setForm((state) => ({ ...state, [key]: value }));

  const submit = (event: FormEvent): void => {
    event.preventDefault();

    const credentials = {
      username: orNull(form.username),
      password: form.password,
      gmail: orNull(form.gmail),
      gmailPassword: form.gmailPassword,
      phone: orNull(form.phone),
      facebookName: orNull(form.facebookName),
      proxyUrl: form.proxyUrl.trim() === '' ? undefined : form.proxyUrl.trim(),
    };

    // Validated with the same schema the server uses, so the message a person
    // sees here is the message the server would have sent.
    const parsed = CreateAccountSchema.safeParse({
      name: form.name,
      displayName: form.displayName === '' ? undefined : form.displayName,
      enabled: form.enabled,
      ...credentials,
    });
    if (!parsed.success) {
      setFieldError(parsed.error.issues[0]?.message ?? 'Check the fields above');
      return;
    }
    setFieldError(null);

    if (account === null) {
      create.mutate(parsed.data, {
        onSuccess: (created) => {
          toast.success(`Added ${created.displayName}`);
          onClose();
        },
      });
      return;
    }

    update.mutate(
      {
        id: account.id,
        patch: {
          name: form.name,
          displayName: form.displayName === '' ? form.name : form.displayName,
          enabled: form.enabled,
          ...credentials,
        },
      },
      {
        onSuccess: () => {
          toast.success('Saved');
          onClose();
        },
      },
    );
  };

  return (
    <Modal
      open={open}
      title={account === null ? 'Add account' : `Edit ${account.name}`}
      description={
        account === null
          ? 'Each account gets a browser profile of its own.'
          : 'Leave a password field empty to keep the stored one.'
      }
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={pending}>
            {account === null ? 'Create account' : 'Save changes'}
          </Button>
        </>
      }
    >
      <form className="grid gap-4" onSubmit={submit}>
        <TextField
          label="Name"
          value={form.name}
          autoFocus
          placeholder="Marketing One"
          hint="Identifies the account here and names its browser profile."
          onChange={(event) => set('name', event.target.value)}
          {...(fieldError === null ? {} : { error: fieldError })}
        />
        <TextField
          label="Display name"
          value={form.displayName}
          placeholder="Optional — defaults to the name"
          onChange={(event) => set('displayName', event.target.value)}
        />

        <Separator />

        <div className="grid gap-4 sm:grid-cols-2">
          <TextField
            label="Facebook username"
            value={form.username}
            placeholder="email, phone or username"
            autoComplete="off"
            onChange={(event) => set('username', event.target.value)}
          />
          <TextField
            label="Facebook password"
            type="password"
            value={form.password}
            placeholder={account?.hasPassword ? '•••••••• (stored)' : ''}
            autoComplete="new-password"
            onChange={(event) => set('password', event.target.value)}
          />
          <TextField
            label="Gmail"
            value={form.gmail}
            autoComplete="off"
            onChange={(event) => set('gmail', event.target.value)}
          />
          <TextField
            label="Gmail password"
            type="password"
            value={form.gmailPassword}
            placeholder={account?.hasGmailPassword ? '•••••••• (stored)' : ''}
            autoComplete="new-password"
            onChange={(event) => set('gmailPassword', event.target.value)}
          />
          <TextField
            label="Phone number"
            value={form.phone}
            onChange={(event) => set('phone', event.target.value)}
          />
          <TextField
            label="Facebook name"
            value={form.facebookName}
            hint="Filled in by a login check when left empty."
            onChange={(event) => set('facebookName', event.target.value)}
          />
        </div>

        <TextField
          label="Proxy"
          value={form.proxyUrl}
          placeholder={
            account?.hasProxy
              ? `${account.proxyServer ?? 'stored'} (stored)`
              : 'host:port:user:pass'
          }
          autoComplete="off"
          hint="This account's browser sends every request through it. Formats: host:port, host:port:user:pass, or scheme://user:pass@host:port."
          onChange={(event) => set('proxyUrl', event.target.value)}
        />

        <CheckboxField
          label="Enabled"
          hint="A disabled account is never scheduled and cannot start a browser."
          checked={form.enabled}
          onCheckedChange={(enabled) => set('enabled', enabled)}
        />

        {failure !== null && <ErrorNotice error={failure} />}
      </form>
    </Modal>
  );
};
