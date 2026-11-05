import { render, screen } from "@testing-library/react";
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
    expect(screen.getByRole("link", { name: /Solara Docs/ })).toHaveAttribute("href", "#/");
    expect(screen.getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  });
});
