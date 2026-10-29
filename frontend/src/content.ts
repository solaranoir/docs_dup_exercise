import type { JSONContent } from "@tiptap/react";

/** Must match FONT_SIZES in backend/app/content.py. */
export const FONT_SIZES = [
  { label: "Small", value: "0.875rem" },
  { label: "Normal", value: "1rem" },
  { label: "Large", value: "1.25rem" },
  { label: "Extra large", value: "1.5rem" },
] as const;

const ALLOWED = new Set<string>(FONT_SIZES.map((s) => s.value));

/** Drop font sizes the server does not accept (e.g. arbitrary sizes from pasted HTML). */
export function normalizeContent(node: JSONContent): JSONContent {
  const out: JSONContent = { ...node };
  if (node.marks) {
    out.marks = node.marks.flatMap((mark) => {
      if (mark.type !== "textStyle") return [mark];
      const size = mark.attrs?.fontSize as string | null | undefined;
      if (size && ALLOWED.has(size)) return [{ type: "textStyle", attrs: { fontSize: size } }];
      return [];
    });
    if (out.marks.length === 0) delete out.marks;
  }
  if (node.content) out.content = node.content.map(normalizeContent);
  return out;
}
