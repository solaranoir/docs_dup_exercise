import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, type DocumentSummary } from "../api";
import { DocumentList } from "./DocumentList";

const doc = (over: Partial<DocumentSummary>): DocumentSummary => ({
  id: "d1",
  title: "POTA K-1234 plan",
  revision: 1,
  owner: { id: 1, display_name: "Kelly" },
  permission: "owner",
  updated_at: "2026-11-05T12:00:00Z",
  ...over,
});

afterEach(() => vi.restoreAllMocks());

describe("DocumentList", () => {
  it("guides a first-time user and sets the tab title", async () => {
    vi.spyOn(api, "listDocuments").mockResolvedValue([]);
    render(<DocumentList />);
    expect(await screen.findByRole("region", { name: "Welcome to Solara Docs" })).toBeInTheDocument();
    expect(screen.getByText("Nothing has been shared with you yet.")).toBeInTheDocument();
    // Guidance points at the page's buttons instead of duplicating them.
    expect(screen.getAllByRole("button", { name: "New document" })).toHaveLength(1);
    expect(document.title).toBe("My Documents · Solara Docs");
  });

  it("hides the guidance once the user owns a document", async () => {
    vi.spyOn(api, "listDocuments").mockResolvedValue([doc({})]);
    render(<DocumentList />);
    expect(await screen.findByRole("link", { name: "POTA K-1234 plan" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Welcome to Solara Docs" })).not.toBeInTheDocument();
  });

  it("still guides a user who only has documents shared with them", async () => {
    vi.spyOn(api, "listDocuments").mockResolvedValue([
      doc({ permission: "viewer", owner: { id: 2, display_name: "Ana" } }),
    ]);
    render(<DocumentList />);
    expect(await screen.findByText("View only · Ana")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Welcome to Solara Docs" })).toBeInTheDocument();
  });
});
