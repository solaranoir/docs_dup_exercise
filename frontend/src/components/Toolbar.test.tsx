import { Editor } from "@tiptap/react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { extensions } from "../editorExtensions";
import { Toolbar } from "./Toolbar";

let editor: Editor;

beforeEach(() => {
  editor = new Editor({
    // Attached to the document so focus moves (Escape → text) can be observed.
    element: document.body.appendChild(document.createElement("div")),
    extensions,
    content: { type: "doc", content: [{ type: "paragraph", content: [{ type: "text", text: "Hello" }] }] },
  });
  editor.commands.selectAll();
});
afterEach(() => {
  editor.destroy();
  document.body.innerHTML = "";
});

describe("Toolbar", () => {
  it("exposes labelled controls in a toolbar", () => {
    render(<Toolbar editor={editor} />);
    expect(screen.getByRole("toolbar", { name: "Formatting" })).toBeInTheDocument();
    for (const name of ["Bold", "Italic", "Underline", "Bulleted list", "Numbered list"]) {
      expect(screen.getByRole("button", { name })).toHaveAttribute("aria-pressed", "false");
    }
    expect(screen.getByRole("combobox", { name: "Block style" })).toHaveValue("paragraph");
    expect(screen.getByRole("combobox", { name: "Text size" })).toHaveValue("1rem");
  });

  it("applies marks, headings, lists and sizes and reflects active state", async () => {
    const user = userEvent.setup();
    render(<Toolbar editor={editor} />);
    await user.click(screen.getByRole("button", { name: "Bold" }));
    expect(screen.getByRole("button", { name: "Bold" })).toHaveAttribute("aria-pressed", "true");

    // Assert on the document: TrailingNode appends an empty paragraph, so a select-all
    // range spans two blocks and isActive() would report false for block types.
    const first = () => editor.getJSON().content![0]!;
    await user.selectOptions(screen.getByRole("combobox", { name: "Block style" }), "h2");
    expect(first()).toMatchObject({ type: "heading", attrs: { level: 2 } });

    act(() => void editor.commands.selectAll());
    await user.selectOptions(screen.getByRole("combobox", { name: "Text size" }), "1.25rem");
    expect(first().content![0]!.marks).toContainEqual({
      type: "textStyle",
      attrs: { fontSize: "1.25rem" },
    });

    act(() => void editor.commands.setTextSelection(2));
    await user.selectOptions(screen.getByRole("combobox", { name: "Block style" }), "paragraph");
    await user.click(screen.getByRole("button", { name: "Bulleted list" }));
    expect(first().type).toBe("bulletList");
  });

  it("is a single Tab stop with Home/End, Escape to the text and Alt+F10 back", async () => {
    const user = userEvent.setup();
    render(<Toolbar editor={editor} />);
    const tabbable = () => screen.getByRole("toolbar").querySelectorAll('[tabindex="0"]');
    expect(tabbable()).toHaveLength(1);

    screen.getByRole("button", { name: "Bold" }).focus();
    await user.keyboard("{End}");
    expect(screen.getByRole("button", { name: "Numbered list" })).toHaveFocus();
    expect(Array.from(tabbable())).toEqual([screen.getByRole("button", { name: "Numbered list" })]);
    await user.keyboard("{Home}");
    expect(screen.getByRole("combobox", { name: "Block style" })).toHaveFocus();
    await user.keyboard("{ArrowRight}{ArrowRight}");
    expect(screen.getByRole("button", { name: "Bold" })).toHaveFocus();

    await user.keyboard("{Escape}");
    await waitFor(() => expect(editor.view.dom).toHaveFocus()); // Tiptap focuses on the next frame
    act(() => {
      editor.view.dom.dispatchEvent(new KeyboardEvent("keydown", { key: "F10", altKey: true, bubbles: true }));
    });
    expect(screen.getByRole("button", { name: "Bold" })).toHaveFocus();
  });

  it("advertises shortcuts to assistive technology", () => {
    render(<Toolbar editor={editor} />);
    expect(screen.getByRole("button", { name: "Bold" })).toHaveAttribute(
      "aria-keyshortcuts",
      "Control+B Meta+B",
    );
  });

  it("moves focus with arrow keys", async () => {
    const user = userEvent.setup();
    render(<Toolbar editor={editor} />);
    screen.getByRole("button", { name: "Bold" }).focus();
    await user.keyboard("{ArrowRight}");
    expect(screen.getByRole("button", { name: "Italic" })).toHaveFocus();
    await user.keyboard("{ArrowLeft}{ArrowLeft}");
    expect(screen.getByRole("combobox", { name: "Text size" })).toHaveFocus();
  });
});
