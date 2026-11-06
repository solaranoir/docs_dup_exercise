import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api, type DocumentFull } from "../api";
import { OrganizePanel } from "./OrganizePanel";

afterEach(() => vi.restoreAllMocks());

const doc = { id: "d1", folder_id: null, tags: [] as string[] } as unknown as DocumentFull;

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const chips = () =>
  screen.queryAllByRole("button", { name: /^Remove tag / }).map((b) => b.getAttribute("aria-label"));

describe("OrganizePanel", () => {
  it("saves quick successive tag changes in order and keeps the newest", async () => {
    vi.spyOn(api, "listFolders").mockResolvedValue([]);
    vi.spyOn(api, "listTags").mockResolvedValue({ tags: [], suggestions: [] });
    const first = deferred<{ tags: string[] }>();
    const second = deferred<{ tags: string[] }>();
    const setTags = vi
      .spyOn(api, "setTags")
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    const user = userEvent.setup();
    render(<OrganizePanel doc={doc} />);
    const input = screen.getByLabelText("Tags", { exact: true });

    const region = screen.getByRole("region", { name: /Organise/ });
    await user.type(input, "pota{Enter}");
    await user.type(input, "cw{Enter}");
    expect(chips()).toEqual(["Remove tag cw", "Remove tag pota"]);
    expect(setTags).toHaveBeenCalledTimes(1); // the second waits for the first
    expect(region).toHaveAttribute("aria-busy", "true");

    first.resolve({ tags: ["pota"] }); // a stale answer must not drop "cw"
    await waitFor(() => expect(setTags).toHaveBeenCalledTimes(2));
    expect(setTags).toHaveBeenLastCalledWith("d1", ["cw", "pota"]);
    expect(chips()).toEqual(["Remove tag cw", "Remove tag pota"]);

    second.resolve({ tags: ["cw", "pota"] });
    await waitFor(() => expect(region).toHaveAttribute("aria-busy", "false"));
    expect(chips()).toEqual(["Remove tag cw", "Remove tag pota"]);
  });

  it("collapses changes made during a save into one save of the newest tags", async () => {
    vi.spyOn(api, "listFolders").mockResolvedValue([]);
    vi.spyOn(api, "listTags").mockResolvedValue({ tags: [], suggestions: [] });
    const first = deferred<{ tags: string[] }>();
    const setTags = vi
      .spyOn(api, "setTags")
      .mockReturnValueOnce(first.promise)
      .mockResolvedValue({ tags: ["a", "b", "c"] } as never);
    const user = userEvent.setup();
    render(<OrganizePanel doc={doc} />);
    const input = screen.getByLabelText("Tags", { exact: true });
    await user.type(input, "a{Enter}");
    await user.type(input, "b{Enter}");
    await user.type(input, "c{Enter}");
    first.resolve({ tags: ["a"] });
    await waitFor(() => expect(chips()).toEqual(["Remove tag a", "Remove tag b", "Remove tag c"]));
    await waitFor(() => expect(screen.getByRole("region", { name: /Organise/ })).toHaveAttribute("aria-busy", "false"));
    expect(setTags.mock.calls.map((c) => c[1])).toEqual([["a"], ["a", "b", "c"]]);
  });

  it("rolls back to the last saved tags when the newest save fails", async () => {
    vi.spyOn(api, "listFolders").mockResolvedValue([]);
    vi.spyOn(api, "listTags").mockResolvedValue({ tags: [], suggestions: [] });
    vi.spyOn(api, "setTags")
      .mockResolvedValueOnce({ tags: ["pota"] } as never)
      .mockRejectedValueOnce(new Error("Too many tags"));
    const user = userEvent.setup();
    render(<OrganizePanel doc={doc} />);
    const input = screen.getByLabelText("Tags", { exact: true });
    await user.type(input, "pota{Enter}");
    await waitFor(() => expect(chips()).toEqual(["Remove tag pota"]));
    await user.type(input, "cw{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many tags");
    expect(chips()).toEqual(["Remove tag pota"]);
  });
});
