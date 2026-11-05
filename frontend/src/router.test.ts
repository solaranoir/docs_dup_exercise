import { afterEach, describe, expect, it, vi } from "vitest";
import { migrateLegacyHash, navigate, navigationGuard, parseRoute, paths } from "./router";

afterEach(() => {
  window.history.replaceState(null, "", "/");
  navigationGuard.dirty = false;
  vi.restoreAllMocks();
});

describe("parseRoute", () => {
  it("recognises the list, documents and unknown paths", () => {
    expect(parseRoute("/")).toEqual({ name: "list" });
    expect(parseRoute("/doc/abc-123")).toEqual({ name: "doc", id: "abc-123" });
    expect(parseRoute("/doc/abc-123/")).toEqual({ name: "doc", id: "abc-123" });
    expect(parseRoute("/doc/")).toEqual({ name: "not-found" });
    expect(parseRoute("/doc/a/b")).toEqual({ name: "not-found" });
    expect(parseRoute("/elsewhere")).toEqual({ name: "not-found" });
  });
});

describe("migrateLegacyHash", () => {
  it("rewrites #/doc/:id to /doc/:id without adding history", () => {
    window.history.replaceState(null, "", "/#/doc/abc");
    const length = window.history.length;
    migrateLegacyHash();
    expect(window.location.pathname).toBe("/doc/abc");
    expect(window.location.hash).toBe("");
    expect(window.history.length).toBe(length);
  });

  it("leaves ordinary fragments alone", () => {
    window.history.replaceState(null, "", "/doc/abc#main");
    migrateLegacyHash();
    expect(window.location.pathname + window.location.hash).toBe("/doc/abc#main");
  });
});

describe("navigate", () => {
  it("pushes the path and notifies subscribers", () => {
    const listener = vi.fn();
    window.addEventListener("solara:navigate", listener);
    expect(navigate(paths.doc("abc"))).toBe(true);
    expect(window.location.pathname).toBe("/doc/abc");
    expect(listener).toHaveBeenCalledOnce();
    window.removeEventListener("solara:navigate", listener);
  });

  it("stays put when the user keeps unsaved edits", () => {
    navigationGuard.dirty = true;
    vi.spyOn(window, "confirm").mockReturnValue(false);
    expect(navigate("/doc/abc")).toBe(false);
    expect(window.location.pathname).toBe("/");
    expect(navigationGuard.dirty).toBe(true);
  });
});
