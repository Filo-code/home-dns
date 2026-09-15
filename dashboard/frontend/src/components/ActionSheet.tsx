import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

/**
 * Native `<dialog>` — free focus trap, Esc-to-close, inert background, no modal library.
 * `confirmLabel`/`onConfirm` are optional: when omitted, only a single dismiss button renders.
 * That's deliberate — an action this phase does not actually perform must never show a
 * "Conferma" button wired to nothing (see QuickActions' admin-action honesty).
 */
export function ActionSheet({
  open,
  title,
  badge,
  description,
  confirmLabel,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  badge?: string;
  description: ReactNode;
  confirmLabel?: string;
  onConfirm?: () => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog ref={ref} className="action-sheet" onClose={onClose}>
      {/* Same jsdom-visibility reasoning as CommandPalette: no content while closed. */}
      {open && (
        <>
          <div className="action-sheet__handle" aria-hidden="true" />
          {badge && <span className="action-sheet__badge">{badge}</span>}
          <h2 className="action-sheet__title">{title}</h2>
          <div className="action-sheet__description">{description}</div>
          <div className="action-sheet__actions">
            {onConfirm && confirmLabel ? (
              <>
                <button type="button" className="button button--secondary" onClick={onClose}>
                  Annulla
                </button>
                <button
                  type="button"
                  className="button button--primary"
                  onClick={() => {
                    onConfirm();
                    onClose();
                  }}
                >
                  {confirmLabel}
                </button>
              </>
            ) : (
              <button type="button" className="button button--primary" onClick={onClose}>
                Ho capito
              </button>
            )}
          </div>
        </>
      )}
    </dialog>
  );
}
