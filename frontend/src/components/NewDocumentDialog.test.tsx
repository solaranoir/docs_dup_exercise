import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, type DocumentFull, type TemplateSummary } from "../api";
import { localDate, NewDocumentDialog, templateTitle } from "./NewDocumentDialog";

const POTA: TemplateSummary = {
  id: "pota-activation-plan",
  version: 1,
  name: "POTA Activation Plan",
  description: "Plan a Parks on the Air activation.",
  sections: [
    { heading: "Park", fields: ["Park reference", "Park name"] },
    { heading: "Operating notes", fields: [] },
  ],
};
const created = { id: "new-doc" } as DocumentFull;

afterEach(() => vi.restoreAllMocks());

function setup() {
  vi.spyOn(api, "listTemplates").mockResolvedValue([POTA]);
  const create = vi.spyOn(api, "createDocument").mockResolvedValue(created);
  const onCreated = vi.fn();
  render(<NewDocumentDialog open onClose={() => {}} onCreated={onCreated} />);
  return { create, onCreated, user: userEvent.setup() };
}

describe("NewDocumentDialog", () => {
  it("creates a blank document by default", async () => {
    const { create, onCreated, user } = setup();
    expect(screen.getByRole("radio", { name: "Blank document" })).toBeChecked();
    await user.click(screen.getByRole("button", { name: "Create" }));
    expect(create).toHaveBeenCalledWith({});
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(created));
  });

  it("previews a template and creates it with a dated title", async () => {
    const { create, user } = setup();
    const radio = await screen.findByRole("radio", { name: "POTA Activation Plan" });
    expect(radio).toHaveAccessibleDescription("Plan a Parks on the Air activation.");
    await user.click(radio);
    const preview = screen.getByRole("region", { name: "Preview" });
    expect(within(preview).getByText("Park")).toBeInTheDocument();
    expect(within(preview).getByText("Park reference · Park name")).toBeInTheDocument();
    expect(within(preview).getByText(templateTitle(POTA))).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Create" }));
    expect(create).toHaveBeenCalledWith({
      template: "pota-activation-plan",
      title: `POTA Activation Plan, ${localDate()}`,
    });
  });

  it("still offers Blank when templates fail to load", async () => {
    vi.spyOn(api, "listTemplates").mockRejectedValue(new Error("offline"));
    render(<NewDocumentDialog open onClose={() => {}} onCreated={() => {}} />);
    expect(await screen.findByText(/Templates couldn't be loaded/)).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Blank document" })).toBeChecked();
  });

  it("shows a create error and lets the user retry", async () => {
    const { create, user } = setup();
    create.mockRejectedValueOnce(new Error("Server unavailable"));
    await user.click(screen.getByRole("button", { name: "Create" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Server unavailable");
    expect(screen.getByRole("button", { name: "Create" })).toBeEnabled();
  });
});

describe("localDate", () => {
  it("uses the local calendar date", () => {
    expect(localDate(new Date(2026, 10, 5, 23, 30))).toBe("2026-11-05");
    expect(localDate(new Date(2027, 0, 9, 0, 5))).toBe("2027-01-09");
  });
});
