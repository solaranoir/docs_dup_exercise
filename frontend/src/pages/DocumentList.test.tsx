import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, type DocumentSummary } from "../api";
import { DocumentList, recentlyOpened, sortDocuments } from "./DocumentList";

const doc = (over: Partial<DocumentSummary>): DocumentSummary => ({
  id: "d1",
  title: "POTA K-1234 plan",
  revision: 1,
  owner: { id: 1, display_name: "Kelly" },
  permission: "owner",
  created_at: "2026-11-01T12:00:00Z",
  updated_at: "2026-11-05T12:00:00Z",
  archived_at: null,
  last_opened_at: null,
  ...over,
});

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

const a = doc({
  id: "a",
  title: "antenna log",
  created_at: "2026-11-03T00:00:00Z",
  updated_at: "2026-11-04T00:00:00Z",
});
const b = doc({
  id: "b",
  title: "Band plan 10",
  created_at: "2026-11-01T00:00:00Z",
  updated_at: "2026-11-06T00:00:00Z",
});
const c = doc({
  id: "c",
  title: "Band plan 9",
  created_at: "2026-11-02T00:00:00Z",
  updated_at: "2026-11-02T00:00:00Z",
});
const ids = (docs: DocumentSummary[]) => docs.map((d) => d.id);

describe("sortDocuments", () => {
  it("sorts by edit time, creation time and title (case-insensitive, numeric-aware)", () => {
    expect(ids(sortDocuments([a, b, c], "edited"))).toEqual(["b", "a", "c"]);
    expect(ids(sortDocuments([a, b, c], "created"))).toEqual(["a", "c", "b"]);
    expect(ids(sortDocuments([b, c, a], "title"))).toEqual(["a", "c", "b"]);
    expect(ids(sortDocuments([a, b, c], "title-desc"))).toEqual([
      "b",
      "c",
      "a",
    ]);
  });
});

describe("recentlyOpened", () => {
  it("lists only opened documents, most recent first, at most five", () => {
    const opened = Array.from({ length: 7 }, (_, i) =>
      doc({ id: `o${i}`, last_opened_at: `2026-11-0${i + 1}T00:00:00Z` }),
    );
    expect(ids(recentlyOpened([a, ...opened]))).toEqual([
      "o6",
      "o5",
      "o4",
      "o3",
      "o2",
    ]);
  });
});

describe("DocumentList", () => {
  it("guides a first-time user and sets the tab title", async () => {
    vi.spyOn(api, "listDocuments").mockResolvedValue([]);
    render(<DocumentList />);
    expect(
      await screen.findByRole("region", { name: "Welcome to Solara Docs" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Nothing has been shared with you yet."),
    ).toBeInTheDocument();
    // Guidance points at the page's buttons instead of duplicating them.
    expect(
      screen.getAllByRole("button", { name: "New document" }),
    ).toHaveLength(1);
    expect(document.title).toBe("My Documents · Solara Docs");
  });

  it("hides the guidance once the user owns a document", async () => {
    vi.spyOn(api, "listDocuments").mockResolvedValue([doc({})]);
    render(<DocumentList />);
    expect(
      await screen.findByRole("link", { name: "POTA K-1234 plan" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: "Welcome to Solara Docs" }),
    ).not.toBeInTheDocument();
  });

  it("still guides a user who only has documents shared with them", async () => {
    vi.spyOn(api, "listDocuments").mockResolvedValue([
      doc({ permission: "viewer", owner: { id: 2, display_name: "Ana" } }),
    ]);
    render(<DocumentList />);
    expect(await screen.findByText("View only · Ana")).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Welcome to Solara Docs" }),
    ).toBeInTheDocument();
  });

  it("shows recently opened documents and remembers the chosen sort", async () => {
    const user = userEvent.setup();
    vi.spyOn(api, "listDocuments").mockResolvedValue([
      a,
      b,
      { ...c, last_opened_at: "2026-11-07T00:00:00Z" },
    ]);
    const { unmount } = render(<DocumentList />);
    const recent = await screen.findByRole("region", {
      name: "Recently opened",
    });
    expect(
      within(recent)
        .getAllByRole("link")
        .map((l) => l.textContent),
    ).toEqual(["Band plan 9"]);
    expect(within(recent).getByText(/^Opened /)).toBeInTheDocument();

    const owned = () =>
      within(screen.getByRole("region", { name: "Owned by me" })).getAllByRole(
        "link",
      );
    expect(owned().map((l) => l.textContent)).toEqual([
      "Band plan 10",
      "antenna log",
      "Band plan 9",
    ]);
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Sort by" }),
      "title",
    );
    expect(owned().map((l) => l.textContent)).toEqual([
      "antenna log",
      "Band plan 9",
      "Band plan 10",
    ]);

    unmount();
    render(<DocumentList />);
    expect(
      await screen.findByRole("combobox", { name: "Sort by" }),
    ).toHaveValue("title");
  });

  it("loads archived documents on request and restores them", async () => {
    const user = userEvent.setup();
    const archived = doc({
      id: "z",
      title: "Old field day",
      archived_at: "2026-11-05T00:00:00Z",
    });
    const list = vi
      .spyOn(api, "listDocuments")
      .mockImplementation(async (wantArchived) =>
        wantArchived ? [archived] : [a],
      );
    const restore = vi
      .spyOn(api, "restoreDocument")
      .mockResolvedValue({ ...archived, archived_at: null, content_json: {} });
    render(<DocumentList />);
    await screen.findByRole("link", { name: "antenna log" });
    expect(list).toHaveBeenCalledTimes(1); // archived list not fetched until asked

    await user.click(
      screen.getByRole("button", { name: "Show archived documents" }),
    );
    const section = await screen.findByRole("region", { name: "Archived" });
    expect(
      within(section).getByRole("link", { name: "Old field day" }),
    ).toBeInTheDocument();

    list.mockImplementation(async (wantArchived) =>
      wantArchived ? [] : [a, { ...archived, archived_at: null }],
    );
    await user.click(
      within(section).getByRole("button", { name: "Restore Old field day" }),
    );
    expect(restore).toHaveBeenCalledWith("z");
    expect(
      await within(section).findByText("No archived documents."),
    ).toBeInTheDocument();
    expect(
      await within(
        screen.getByRole("region", { name: "Owned by me" }),
      ).findByRole("link", { name: "Old field day" }),
    ).toBeInTheDocument();
  });
});
