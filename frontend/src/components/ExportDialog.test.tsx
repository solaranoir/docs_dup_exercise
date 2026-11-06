import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, dispositionFilename } from "../api";
import * as download from "../download";
import { ExportDialog } from "./ExportDialog";

afterEach(() => vi.restoreAllMocks());

function renderDialog(dirty = false) {
  const onClose = vi.fn();
  render(
    <ExportDialog open onClose={onClose} documentId="d1" title="K-4389 plan" dirty={dirty} />,
  );
  return { onClose, user: userEvent.setup() };
}

describe("ExportDialog", () => {
  it("downloads Markdown with the server's file name", async () => {
    const blob = new Blob(["# K-4389 plan\n"]);
    const exportDoc = vi.spyOn(api, "exportDocument").mockResolvedValue({ blob, filename: "k-4389-plan.md", headers: new Headers() });
    const save = vi.spyOn(download, "saveFile").mockImplementation(() => {});
    const { onClose, user } = renderDialog();
    await user.click(screen.getByRole("button", { name: "Download Markdown" }));
    expect(exportDoc).toHaveBeenCalledWith("d1");
    await waitFor(() => expect(save).toHaveBeenCalledWith(blob, "k-4389-plan.md"));
    expect(onClose).toHaveBeenCalled();
  });

  it("asks for a save first when there are unsaved edits", () => {
    renderDialog(true);
    const button = screen.getByRole("button", { name: "Download Markdown" });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription("Save your changes first: the export uses the saved version.");
  });

  it("shows the server's message when the export fails", async () => {
    vi.spyOn(api, "exportDocument").mockRejectedValue(new ApiError(503, "Attachments are temporarily unavailable."));
    const { onClose, user } = renderDialog();
    await user.click(screen.getByRole("button", { name: "Download Markdown" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Attachments are temporarily unavailable.");
    expect(onClose).not.toHaveBeenCalled();
  });

  it("closes, then prints with the document title", async () => {
    const print = vi.spyOn(download, "printDocument").mockImplementation(() => {});
    const { onClose, user } = renderDialog(true); // printing shows what's on screen, saved or not
    await user.click(screen.getByRole("button", { name: "Print or save as PDF" }));
    expect(onClose).toHaveBeenCalled();
    await waitFor(() => expect(print).toHaveBeenCalledWith("K-4389 plan"));
  });
});

describe("dispositionFilename", () => {
  it("prefers the UTF-8 name and falls back sensibly", () => {
    expect(dispositionFilename(`attachment; filename="ecoute.md"; filename*=UTF-8''%C3%A9coute.md`, "x")).toBe("écoute.md");
    expect(dispositionFilename('attachment; filename="plan.zip"', "x")).toBe("plan.zip");
    expect(dispositionFilename(`attachment; filename="a.md"; filename*=UTF-8''%E0%A4`, "x")).toBe("a.md");
    expect(dispositionFilename(null, "fallback.md")).toBe("fallback.md");
  });
});

describe("printDocument", () => {
  it("uses the document title while printing and restores the tab title after", () => {
    document.title = "K-4389 plan · Solara Docs";
    const print = vi.spyOn(window, "print").mockImplementation(() => {
      expect(document.title).toBe("K-4389 plan");
    });
    download.printDocument("K-4389 plan");
    expect(print).toHaveBeenCalled();
    window.dispatchEvent(new Event("afterprint"));
    expect(document.title).toBe("K-4389 plan · Solara Docs");
  });
});
