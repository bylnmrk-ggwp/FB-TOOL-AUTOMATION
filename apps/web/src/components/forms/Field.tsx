import type { InputHTMLAttributes, ReactElement, ReactNode, TextareaHTMLAttributes } from 'react';
import { useId } from 'react';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';

interface FieldShellProps {
  label: string;
  hint?: string;
  error?: string;
  children: (id: string, describedBy: string | undefined) => ReactNode;
}

/**
 * Label, control and message in one place, so every form reports a problem
 * the same way and every control keeps its label association.
 */
const FieldShell = ({ label, hint, error, children }: FieldShellProps): ReactElement => {
  const id = useId();
  const messageId = `${id}-message`;
  const hasMessage = error !== undefined || hint !== undefined;

  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children(id, hasMessage ? messageId : undefined)}
      {error !== undefined ? (
        <p id={messageId} className="text-xs text-destructive">
          {error}
        </p>
      ) : (
        hint !== undefined && (
          <p id={messageId} className="text-xs text-muted-foreground">
            {hint}
          </p>
        )
      )}
    </div>
  );
};

type FieldProps = { label: string; hint?: string; error?: string };

export const TextField = ({
  label,
  hint,
  error,
  ...rest
}: Omit<InputHTMLAttributes<HTMLInputElement>, 'id'> & FieldProps): ReactElement => (
  <FieldShell
    label={label}
    {...(hint === undefined ? {} : { hint })}
    {...(error === undefined ? {} : { error })}
  >
    {(id, describedBy) => (
      <Input id={id} aria-invalid={error !== undefined} aria-describedby={describedBy} {...rest} />
    )}
  </FieldShell>
);

export const TextAreaField = ({
  label,
  hint,
  error,
  ...rest
}: Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'id'> & FieldProps): ReactElement => (
  <FieldShell
    label={label}
    {...(hint === undefined ? {} : { hint })}
    {...(error === undefined ? {} : { error })}
  >
    {(id, describedBy) => (
      <Textarea
        id={id}
        className="min-h-36 leading-relaxed"
        aria-invalid={error !== undefined}
        aria-describedby={describedBy}
        {...rest}
      />
    )}
  </FieldShell>
);

interface NativeSelectProps {
  value: string;
  options: ReadonlyArray<{ value: string; label: string }>;
  onValueChange: (value: string) => void;
  id?: string;
  className?: string;
  disabled?: boolean;
  'aria-label'?: string;
  'aria-invalid'?: boolean;
  'aria-describedby'?: string | undefined;
}

/**
 * The list cannot carry an empty value ("any", "no reaction"), so the empty
 * string travels under a stand-in and is translated back at the edges.
 */
const EMPTY = '__empty__';
const toItem = (value: string): string => (value === '' ? EMPTY : value);
const fromItem = (value: string): string => (value === EMPTY ? '' : value);

/**
 * The application's one dropdown: a styled list that opens the same way in
 * every theme, instead of the platform's own control, which drew a light
 * list under a dark page.
 */
export const NativeSelect = ({
  value,
  options,
  onValueChange,
  id,
  className,
  disabled,
  ...aria
}: NativeSelectProps): ReactElement => (
  <Select
    value={toItem(value)}
    onValueChange={(next) => onValueChange(fromItem(next))}
    {...(disabled === undefined ? {} : { disabled })}
  >
    <SelectTrigger
      {...(id === undefined ? {} : { id })}
      className={cn('w-full', className)}
      aria-label={aria['aria-label']}
      aria-invalid={aria['aria-invalid']}
      aria-describedby={aria['aria-describedby']}
    >
      <SelectValue />
    </SelectTrigger>
    <SelectContent>
      {options.map((option) => (
        <SelectItem key={option.value} value={toItem(option.value)}>
          {option.label}
        </SelectItem>
      ))}
    </SelectContent>
  </Select>
);

export const SelectField = ({
  label,
  hint,
  error,
  options,
  ...rest
}: Omit<NativeSelectProps, 'id'> & FieldProps): ReactElement => (
  <FieldShell
    label={label}
    {...(hint === undefined ? {} : { hint })}
    {...(error === undefined ? {} : { error })}
  >
    {(id, describedBy) => (
      <NativeSelect
        id={id}
        options={options}
        aria-invalid={error !== undefined}
        aria-describedby={describedBy}
        {...rest}
      />
    )}
  </FieldShell>
);

export const CheckboxField = ({
  label,
  hint,
  checked,
  onCheckedChange,
  disabled,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
}): ReactElement => {
  const id = useId();

  return (
    <div className="flex items-start gap-3">
      <Checkbox
        id={id}
        checked={checked}
        disabled={disabled}
        onCheckedChange={(value) => onCheckedChange(value === true)}
        className="mt-0.5"
      />
      <div className="grid gap-1">
        <Label htmlFor={id} className="font-normal">
          {label}
        </Label>
        {hint !== undefined && <p className="text-xs text-muted-foreground">{hint}</p>}
      </div>
    </div>
  );
};
