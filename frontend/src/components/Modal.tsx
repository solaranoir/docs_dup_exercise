import { useEffect, useId, useRef, type ReactNode } from "react";

/** Native <dialog>: focus trapping, Esc to close and inert background come from the browser. */
export function Modal({
  title,
  open,
  onClose,
  children,
}: {
  title: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  // Unique per dialog: several modals can be mounted on one page.
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal?.();
    if (!open && dialog.open) dialog.close?.();
  }, [open]);

  return (
    <dialog ref={ref} className="modal" aria-labelledby={titleId} onClose={onClose}>
      <div className="modal-head">
        <h2 id={titleId}>{title}</h2>
        <button type="button" aria-label="Close" onClick={onClose}>
          ×
        </button>
      </div>
      {open && children}
    </dialog>
  );
}
