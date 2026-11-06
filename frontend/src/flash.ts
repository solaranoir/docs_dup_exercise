/** A one-shot message carried across an in-app navigation (e.g. "Moved to Trash · Undo"). */
export interface Flash {
  message: string;
  /** The document that was moved to the Trash, so the next page can offer Undo. */
  trashedId?: string;
}

let pending: Flash | null = null;

export function setFlash(flash: Flash): void {
  pending = flash;
}

/** The pending message, without clearing it (safe in render and StrictMode's double calls). */
export function peekFlash(): Flash | null {
  return pending;
}

export function clearFlash(): void {
  pending = null;
}
