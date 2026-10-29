import { describe, expect, it } from "vitest";
import { normalizeContent } from "./content";

describe("normalizeContent", () => {
  it("keeps allowed font sizes and drops unknown ones", () => {
    const doc = {
      type: "doc",
      content: [
        {
          type: "paragraph",
          content: [
            { type: "text", text: "big", marks: [{ type: "textStyle", attrs: { fontSize: "1.5rem" } }] },
            { type: "text", text: "pasted", marks: [{ type: "textStyle", attrs: { fontSize: "13px" } }, { type: "bold" }] },
            { type: "text", text: "plain", marks: [{ type: "textStyle", attrs: { fontSize: null } }] },
          ],
        },
      ],
    };
    const [big, pasted, plain] = normalizeContent(doc).content![0]!.content!;
    expect(big!.marks).toEqual([{ type: "textStyle", attrs: { fontSize: "1.5rem" } }]);
    expect(pasted!.marks).toEqual([{ type: "bold" }]);
    expect(plain!.marks).toBeUndefined();
  });
});
