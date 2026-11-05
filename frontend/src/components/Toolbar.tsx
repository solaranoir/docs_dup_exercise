import { useEditorState, type Editor } from "@tiptap/react";
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { FONT_SIZES } from "../content";

type Block = "paragraph" | "h1" | "h2" | "h3";

function currentBlock(editor: Editor): Block {
  for (const level of [1, 2, 3] as const) {
    if (editor.isActive("heading", { level })) return `h${level}`;
  }
  return "paragraph";
}

/** Alt+F10 in the editor focuses the toolbar (the convention in Google Docs, CKEditor, TinyMCE). */
export const TOOLBAR_SHORTCUT = "Alt+F10";

/**
 * Formatting toolbar, WAI-ARIA toolbar pattern (DOC-015): one Tab stop (roving tabindex),
 * Left/Right/Home/End move between controls, Escape returns to the text. Alt+F10 in the
 * editor comes back to the control used last.
 */
export function Toolbar({ editor }: { editor: Editor }) {
  const ref = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(0);
  const controls = () => Array.from(ref.current?.querySelectorAll<HTMLElement>("button, select") ?? []);

  // Roving tabindex: only the remembered control is in the Tab order.
  useEffect(() => {
    controls().forEach((el, i) => (el.tabIndex = i === active ? 0 : -1));
  });

  useEffect(() => {
    const dom = editor.view.dom;
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.altKey && event.key === "F10") {
        event.preventDefault();
        controls()[active]?.focus();
      }
    };
    dom.addEventListener("keydown", onKey);
    return () => dom.removeEventListener("keydown", onKey);
  }, [editor, active]);
  const state = useEditorState({
    editor,
    selector: ({ editor: e }) => ({
      bold: e.isActive("bold"),
      italic: e.isActive("italic"),
      underline: e.isActive("underline"),
      bulletList: e.isActive("bulletList"),
      orderedList: e.isActive("orderedList"),
      block: currentBlock(e),
      fontSize: (e.getAttributes("textStyle").fontSize as string | undefined) ?? "1rem",
    }),
  });

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      editor.commands.focus();
      return;
    }
    const items = controls();
    const index = items.indexOf(document.activeElement as HTMLElement);
    if (index < 0) return;
    let next: number;
    if (event.key === "ArrowRight") next = (index + 1) % items.length;
    else if (event.key === "ArrowLeft") next = (index - 1 + items.length) % items.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = items.length - 1;
    else return;
    event.preventDefault();
    setActive(next);
    items[next]?.focus();
  };

  const setBlock = (block: Block) => {
    const chain = editor.chain().focus();
    if (block === "paragraph") chain.setParagraph().run();
    else chain.setHeading({ level: Number(block[1]) as 1 | 2 | 3 }).run();
  };

  const setSize = (size: string) => {
    const chain = editor.chain().focus();
    if (size === "1rem") chain.unsetFontSize().run();
    else chain.setFontSize(size).run();
  };

  const toggle = (
    label: string,
    shortcut: string,
    pressed: boolean,
    run: () => void,
    face: ReactNode,
  ) => (
    <button
      type="button"
      aria-label={label}
      aria-pressed={pressed}
      aria-keyshortcuts={ariaShortcut(shortcut)}
      title={`${label} (${displayShortcut(shortcut)})`}
      onClick={run}
      // Keep the text selection in the editor when clicking a button.
      onMouseDown={(e) => e.preventDefault()}
    >
      {face}
    </button>
  );
  const chain = () => editor.chain().focus();

  return (
    <div
      className="toolbar"
      role="toolbar"
      aria-label="Formatting"
      ref={ref}
      onKeyDown={onKeyDown}
      // Clicking or tabbing into a control makes it the one Tab/Alt+F10 return to.
      onFocus={(e) => {
        const index = controls().indexOf(e.target as HTMLElement);
        if (index >= 0) setActive(index);
      }}
    >
      <select aria-label="Block style" value={state.block} onChange={(e) => setBlock(e.target.value as Block)}>
        <option value="paragraph">Paragraph</option>
        <option value="h1">Heading 1</option>
        <option value="h2">Heading 2</option>
        <option value="h3">Heading 3</option>
      </select>
      <select aria-label="Text size" value={state.fontSize} onChange={(e) => setSize(e.target.value)}>
        {FONT_SIZES.map((s) => (
          <option key={s.value} value={s.value}>
            {s.label}
          </option>
        ))}
      </select>
      <span className="sep" aria-hidden="true" />
      {toggle("Bold", "Mod+B", state.bold, () => chain().toggleBold().run(), <b>B</b>)}
      {toggle("Italic", "Mod+I", state.italic, () => chain().toggleItalic().run(), <i>I</i>)}
      {toggle("Underline", "Mod+U", state.underline, () => chain().toggleUnderline().run(), <u>U</u>)}
      <span className="sep" aria-hidden="true" />
      {toggle("Bulleted list", "Mod+Shift+8", state.bulletList, () => chain().toggleBulletList().run(), "• List")}
      {toggle("Numbered list", "Mod+Shift+7", state.orderedList, () => chain().toggleOrderedList().run(), "1. List")}
    </div>
  );
}

const IS_MAC = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

/** "Mod+Shift+8" → "Control+Shift+8 Meta+Shift+8" (aria-keyshortcuts lists alternatives). */
function ariaShortcut(shortcut: string): string {
  return shortcut.includes("Mod+")
    ? `${shortcut.replace("Mod+", "Control+")} ${shortcut.replace("Mod+", "Meta+")}`
    : shortcut;
}

/** "Mod+B" → "Ctrl+B", or "⌘B" on Apple platforms. */
export function displayShortcut(shortcut: string): string {
  if (!IS_MAC) return shortcut.replace("Mod+", "Ctrl+");
  return shortcut.replace("Mod+", "⌘").replace("Shift+", "⇧").replace("Alt+", "⌥");
}
