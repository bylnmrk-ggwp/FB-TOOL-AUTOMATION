import type {
  InputHTMLAttributes,
  ReactElement,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react';
import { useId } from 'react';
import { ChevronDown } from 'lucide-react';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
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

/**
 * A native <select>, styled to match the inputs. Native because filters are
 * changed constantly and keyboard users expect the platform control there;
 * the Radix select is reserved for places where option rendering matters.
 */
export const NativeSelect = ({
  className,
  options,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement> & {
  options: ReadonlyArray<{ value: string; label: string }>;
}): ReactElement => (
  <div className="relative">
    <select
      className={cn(
        'h-9 w-full appearance-none rounded-md border border-input bg-transparent py-1 pr-8 pl-3 text-sm shadow-xs outline-none transition-[color,box-shadow] focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-input/30',
        className,
      )}
      {...rest}
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
    <ChevronDown
      className="pointer-events-none absolute top-1/2 right-2.5 size-4 -translate-y-1/2 text-muted-foreground"
      aria-hidden="true"
    />
  </div>
);

export const SelectField = ({
  label,
  hint,
  error,
  options,
  ...rest
}: Omit<SelectHTMLAttributes<HTMLSelectElement>, 'id'> &
  FieldProps & { options: ReadonlyArray<{ value: string; label: string }> }): ReactElement => (
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
