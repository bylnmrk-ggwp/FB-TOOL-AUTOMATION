import type { ReactElement, ReactNode } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { cn } from '@/lib/utils';

interface ModalProps {
  open: boolean;
  title: string;
  description?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  /** `wide` fits a payload or a result without scrolling sideways. */
  size?: 'default' | 'wide';
}

/**
 * A thin shape over the shadcn dialog, so pages open one with `open` and
 * `onClose` and never repeat the header/footer scaffolding.
 */
export const Modal = ({
  open,
  title,
  description,
  onClose,
  children,
  footer,
  size = 'default',
}: ModalProps): ReactElement => (
  <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
    <DialogContent className={cn(size === 'wide' && 'sm:max-w-2xl')}>
      <DialogHeader>
        <DialogTitle>{title}</DialogTitle>
        {description !== undefined ? (
          <DialogDescription>{description}</DialogDescription>
        ) : (
          <DialogDescription className="sr-only">{title}</DialogDescription>
        )}
      </DialogHeader>
      <div className="grid max-h-[60vh] gap-4 overflow-y-auto pr-1">{children}</div>
      {footer !== undefined && <DialogFooter>{footer}</DialogFooter>}
    </DialogContent>
  </Dialog>
);
