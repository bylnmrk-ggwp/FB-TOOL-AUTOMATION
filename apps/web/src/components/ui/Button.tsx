import type { ButtonHTMLAttributes, ReactElement, ReactNode } from 'react';
import './Button.css';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: 'sm' | 'md';
  loading?: boolean;
  children: ReactNode;
}

export const Button = ({
  variant = 'secondary',
  size = 'md',
  loading = false,
  disabled,
  children,
  className,
  ...rest
}: ButtonProps): ReactElement => (
  <button
    type="button"
    className={`btn btn--${variant} btn--${size}${className === undefined ? '' : ` ${className}`}`}
    // A button that is working is disabled, so a double click cannot fire the
    // same mutation twice.
    disabled={disabled === true || loading}
    aria-busy={loading}
    {...rest}
  >
    {loading && <span className="btn__spinner" aria-hidden="true" />}
    {children}
  </button>
);
