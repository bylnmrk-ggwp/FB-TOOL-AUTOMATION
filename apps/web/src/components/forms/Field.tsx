import type {
  InputHTMLAttributes,
  ReactElement,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react';
import { useId } from 'react';
import './Field.css';

interface FieldShellProps {
  label: string;
  hint?: string;
  error?: string;
  children: (id: string) => ReactNode;
}

/**
 * Label, control and message in one place, so every form in the application
 * reports a problem the same way and every control keeps its label association.
 */
const FieldShell = ({ label, hint, error, children }: FieldShellProps): ReactElement => {
  const id = useId();

  return (
    <div className={`field${error === undefined ? '' : ' field--invalid'}`}>
      <label className="field__label" htmlFor={id}>
        {label}
      </label>
      {children(id)}
      {error !== undefined && <p className="field__error">{error}</p>}
      {error === undefined && hint !== undefined && <p className="field__hint">{hint}</p>}
    </div>
  );
};

type TextFieldProps = Omit<InputHTMLAttributes<HTMLInputElement>, 'id'> & {
  label: string;
  hint?: string;
  error?: string;
};

export const TextField = ({ label, hint, error, ...rest }: TextFieldProps): ReactElement => (
  <FieldShell
    label={label}
    {...(hint === undefined ? {} : { hint })}
    {...(error === undefined ? {} : { error })}
  >
    {(id) => (
      <input id={id} className="field__control" aria-invalid={error !== undefined} {...rest} />
    )}
  </FieldShell>
);

type TextAreaFieldProps = Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'id'> & {
  label: string;
  hint?: string;
  error?: string;
};

export const TextAreaField = ({
  label,
  hint,
  error,
  ...rest
}: TextAreaFieldProps): ReactElement => (
  <FieldShell
    label={label}
    {...(hint === undefined ? {} : { hint })}
    {...(error === undefined ? {} : { error })}
  >
    {(id) => (
      <textarea
        id={id}
        className="field__control field__control--area"
        aria-invalid={error !== undefined}
        {...rest}
      />
    )}
  </FieldShell>
);

type SelectFieldProps = Omit<SelectHTMLAttributes<HTMLSelectElement>, 'id'> & {
  label: string;
  hint?: string;
  error?: string;
  options: ReadonlyArray<{ value: string; label: string }>;
};

export const SelectField = ({
  label,
  hint,
  error,
  options,
  ...rest
}: SelectFieldProps): ReactElement => (
  <FieldShell
    label={label}
    {...(hint === undefined ? {} : { hint })}
    {...(error === undefined ? {} : { error })}
  >
    {(id) => (
      <select id={id} className="field__control" aria-invalid={error !== undefined} {...rest}>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    )}
  </FieldShell>
);

export const CheckboxField = ({
  label,
  hint,
  ...rest
}: Omit<InputHTMLAttributes<HTMLInputElement>, 'id' | 'type'> & {
  label: string;
  hint?: string;
}): ReactElement => {
  const id = useId();

  return (
    <div className="field field--inline">
      <input id={id} type="checkbox" className="field__checkbox" {...rest} />
      <div>
        <label className="field__label field__label--inline" htmlFor={id}>
          {label}
        </label>
        {hint !== undefined && <p className="field__hint">{hint}</p>}
      </div>
    </div>
  );
};
