import { useEffect, useRef, type ReactElement, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import './Modal.css';

interface ModalProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
}

/**
 * A native <dialog>, so focus trapping, Escape and the backdrop come from the
 * platform instead of from hand-written key handlers.
 */
export const Modal = ({
  open,
  title,
  onClose,
  children,
  footer,
}: ModalProps): ReactElement | null => {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog === null) return;

    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  useEffect(() => {
    const dialog = ref.current;
    if (dialog === null) return undefined;

    const handleCancel = (event: Event): void => {
      event.preventDefault();
      onClose();
    };

    dialog.addEventListener('cancel', handleCancel);
    return () => dialog.removeEventListener('cancel', handleCancel);
  }, [onClose]);

  return createPortal(
    <dialog ref={ref} className="modal" onClose={onClose}>
      <header className="modal__header">
        <h2 className="modal__title">{title}</h2>
        <button type="button" className="modal__close" onClick={onClose} aria-label="Close">
          ×
        </button>
      </header>
      <div className="modal__body">{children}</div>
      {footer !== undefined && <footer className="modal__footer">{footer}</footer>}
    </dialog>,
    document.body,
  );
};
