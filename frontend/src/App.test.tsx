import { render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";
import { App } from "./App";

afterEach(() => vi.restoreAllMocks());

describe("App header", () => {
  it("links back to the Solara Radio Tools library and shows the Solara Docs brand", async () => {
    vi.spyOn(api, "me").mockResolvedValue({ id: 1, display_name: "Kelly", email: "k@example.com", login_key: null });
    vi.spyOn(api, "listDocuments").mockResolvedValue([]);
    render(<App />);
    const back = await screen.findByRole("link", { name: "Solara Radio Tools" });
    expect(back).toHaveAttribute("href", "https://solararadio.netlify.app/tools");
    expect(screen.getByRole("link", { name: /Solara Docs/ })).toHaveAttribute("href", "/");
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  });
});

describe("Session ended", () => {
  const kelly = { id: 1, display_name: "Kelly", email: "k@example.com", login_key: null };
  const respond = (status: number, body: unknown = {}) =>
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(body), { status }));

  it("keeps the page and offers sign-in when a call gets 401, then clears after success", async () => {
    vi.spyOn(api, "me").mockResolvedValue(kelly);
    vi.spyOn(api, "listDocuments").mockResolvedValue([]);
    render(<App />);
    await screen.findByRole("button", { name: "Sign out" });
    expect(screen.queryByRole("alert")).toBeNull();

    respond(401, { detail: "Not signed in" });
    await expect(api.listFolders()).rejects.toThrow();
    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent("You've been signed out.");
    expect(banner).toHaveTextContent("Anything you haven't saved is still on this page.");
    const link = within(banner).getByRole("link", { name: "Sign in in a new tab" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument(); // page kept

    respond(200, []);
    await api.listFolders();
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });

  it("does not treat the sign-in check itself as an ended session", async () => {
    respond(401, { detail: "Not signed in" });
    vi.spyOn(api, "authMethods").mockResolvedValue({ providers: [], demo: false } as never);
    render(<App />);
    await waitFor(() => expect(screen.queryByText("You've been signed out.")).toBeNull());
    await expect(api.me()).rejects.toThrow();
    expect(screen.queryByText(/You've been signed out/)).toBeNull();
  });
});
