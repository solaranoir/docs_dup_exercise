import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SaveStatus, type SaveState } from "./SaveStatus";

describe("SaveStatus", () => {
  it.each<[SaveState, string]>([
    ["saved", "All changes saved"],
    ["unsaved", "Unsaved changes"],
    ["saving", "Saving…"],
    ["error", "Save failed"],
    ["conflict", "Conflict — newer version exists"],
  ])("announces %s politely", (state, text) => {
    render(<SaveStatus state={state} />);
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent(text);
    expect(status).toHaveAttribute("aria-live", "polite");
  });
});
