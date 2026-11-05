import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(cleanup);

// jsdom has no layout. ProseMirror measures the selection (Range/Text getClientRects) when it
// scrolls it into view, which happens once an editor is attached to the document.
const emptyRects = () => Object.assign([], { item: () => null }) as unknown as DOMRectList;
const zeroRect = () => new DOMRect(0, 0, 0, 0);
for (const proto of [Range.prototype, Text.prototype] as unknown as Record<string, unknown>[]) {
  proto.getClientRects ??= emptyRects;
  proto.getBoundingClientRect ??= zeroRect;
}
