import { useEffect, useState, type FormEvent, type ReactElement } from 'react';
import { CreateAccountSchema, type Account } from '@fb/shared';
import { Button } from '../../../components/ui/Button';
import { ErrorNotice } from '../../../components/ui/Feedback';
import { CheckboxField, TextField } from '../../../components/forms/Field';
import { Modal } from '../../../components/dialogs/Modal';
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
}

const emptyForm: FormState = { name: '', displayName: '', enabled: true };

/**
 * One dialog for both creating and editing. The difference is which mutation
 * runs and which fields the server will accept, not a second form.
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
        : { name: account.name, displayName: account.displayName, enabled: account.enabled },
    );
    // Resetting depends only on which account the dialog was opened for.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, account]);

  const submit = (event: FormEvent): void => {
    event.preventDefault();

    // Validated with the same schema the server uses, so the message a person
    // sees here is the message the server would have sent.
    const parsed = CreateAccountSchema.safeParse({
      name: form.name,
      displayName: form.displayName === '' ? undefined : form.displayName,
      enabled: form.enabled,
    });

    if (!parsed.success) {
      setFieldError(parsed.error.issues[0]?.message ?? 'Check the fields above');
      return;
    }
    setFieldError(null);

    if (account === null) {
      create.mutate(parsed.data, { onSuccess: onClose });
      return;
    }

    update.mutate(
      {
        id: account.id,
        patch: {
          name: form.name,
          displayName: form.displayName === '' ? form.name : form.displayName,
          enabled: form.enabled,
        },
      },
      { onSuccess: onClose },
    );
  };

  return (
    <Modal
      open={open}
      title={account === null ? 'Add account' : `Edit ${account.name}`}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button variant="primary" onClick={submit} loading={pending}>
            {account === null ? 'Create account' : 'Save changes'}
          </Button>
        </>
      }
    >
      <form className="stack" onSubmit={submit}>
        <TextField
          label="Name"
          value={form.name}
          autoFocus
          placeholder="Marketing One"
          hint="Used to identify the account, and to name its browser profile."
          onChange={(event) => setForm((state) => ({ ...state, name: event.target.value }))}
          {...(fieldError === null ? {} : { error: fieldError })}
        />

        <TextField
          label="Display name"
          value={form.displayName}
          placeholder="Optional — defaults to the name"
          onChange={(event) => setForm((state) => ({ ...state, displayName: event.target.value }))}
        />

        <CheckboxField
          label="Enabled"
          hint="A disabled account is never scheduled and cannot start a browser."
          checked={form.enabled}
          onChange={(event) => setForm((state) => ({ ...state, enabled: event.target.checked }))}
        />

        {failure !== null && <ErrorNotice error={failure} />}
      </form>
    </Modal>
  );
};
