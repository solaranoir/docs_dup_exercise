import { displayShortcut, TOOLBAR_SHORTCUT } from "./Toolbar";

const SHORTCUTS: [string, string][] = [
  ["Mod+S", "Save"],
  ["Mod+B", "Bold"],
  ["Mod+I", "Italic"],
  ["Mod+U", "Underline"],
  ["Mod+Shift+8", "Bulleted list"],
  ["Mod+Shift+7", "Numbered list"],
  ["Tab / Shift+Tab", "Indent / outdent a list item"],
  [TOOLBAR_SHORTCUT, "Move to the formatting toolbar"],
  ["Escape", "From the toolbar, return to the text"],
];

/** Discoverable list of editor shortcuts (DOC-015). A native <details>, so it needs no script. */
export function KeyboardHelp() {
  return (
    <details className="keyboard-help">
      <summary>Keyboard shortcuts</summary>
      <dl>
        {SHORTCUTS.map(([keys, action]) => (
          <div key={keys}>
            <dt>
              <kbd>{displayShortcut(keys)}</kbd>
            </dt>
            <dd>{action}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
