export type SaveState = "saved" | "unsaved" | "saving" | "error" | "conflict";

const LABELS: Record<SaveState, string> = {
  saved: "All changes saved",
  unsaved: "Unsaved changes",
  saving: "Saving…",
  error: "Save failed",
  conflict: "Conflict — newer version exists",
};

export function SaveStatus({ state }: { state: SaveState }) {
  return (
    <span className={`save-status save-${state}`} role="status" aria-live="polite" data-state={state}>
      {LABELS[state]}
    </span>
  );
}
