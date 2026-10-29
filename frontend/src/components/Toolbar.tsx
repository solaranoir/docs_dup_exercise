import { useEditorState, type Editor } from "@tiptap/react";
import { useRef, type KeyboardEvent, type ReactNode } from "react";
import { FONT_SIZES } from "../content";

type Block = "paragraph" | "h1" | "h2" | "h3";

function currentBlock(editor: Editor): Block {
  for (const level of [1, 2, 3] as const) {
    if (editor.isActive("heading", { level })) return `h${level}`;
  }
  return "paragraph";
}

/** Formatting toolbar. Arrow keys move focus between controls (WAI-ARIA toolbar pattern). */
export function Toolbar({ editor }: { editor: Editor }) {
  const ref = useRef<HTMLDivElement>(null);
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
    if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
    const items = Array.from(ref.current?.querySelectorAll<HTMLElement>("button, select") ?? []);
    const index = items.indexOf(document.activeElement as HTMLElement);
    if (index < 0) return;
    event.preventDefault();
    const next = (index + (event.key === "ArrowRight" ? 1 : -1) + items.length) % items.length;
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
    active: boolean,
    run: () => void,
    face: ReactNode,
  ) => (
    <button
      type="button"
      aria-label={label}
      aria-pressed={active}
      title={`${label} (${shortcut})`}
      onClick={run}
      // Keep the text selection in the editor when clicking a button.
      onMouseDown={(e) => e.preventDefault()}
    >
      {face}
    </button>
  );
  const chain = () => editor.chain().focus();

  return (
    <div className="toolbar" role="toolbar" aria-label="Formatting" ref={ref} onKeyDown={onKeyDown}>
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
