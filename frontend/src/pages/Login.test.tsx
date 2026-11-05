import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import { Login } from "./Login";

afterEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
});

describe("Login", () => {
  it("offers configured providers as full-page links and hides demo identities", async () => {
    vi.spyOn(api, "authMethods").mockResolvedValue({
      providers: [
        { name: "github", label: "GitHub" },
        { name: "google", label: "Google" },
      ],
      demo: false,
    });
    const demoUsers = vi.spyOn(api, "demoUsers");
    render(<Login onLogin={() => {}} />);

    const github = await screen.findByRole("link", { name: "Sign in with GitHub" });
    expect(github).toHaveAttribute("href", "/api/auth/github/start");
    expect(screen.getByRole("link", { name: "Sign in with Google" })).toHaveAttribute(
      "href",
      "/api/auth/google/start",
    );
    expect(screen.queryByText("Demo identities")).not.toBeInTheDocument();
    expect(demoUsers).not.toHaveBeenCalled();
  });

  it("shows demo identities only when the server enables them", async () => {
    vi.spyOn(api, "authMethods").mockResolvedValue({ providers: [], demo: true });
    vi.spyOn(api, "demoUsers").mockResolvedValue([
      { id: 1, login_key: "alice", display_name: "Alice (owner)", email: null },
    ]);
    render(<Login onLogin={() => {}} />);
    expect(await screen.findByRole("button", { name: "Alice (owner)" })).toBeInTheDocument();
  });

  it("explains when no sign-in method is available", async () => {
    vi.spyOn(api, "authMethods").mockResolvedValue({ providers: [], demo: false });
    render(<Login onLogin={() => {}} />);
    expect(await screen.findByText("Sign-in is not available yet.")).toBeInTheDocument();
  });

  it.each([
    ["not_invited", /isn't invited/],
    ["unverified_email", /verified email/],
    ["cancelled", /cancelled/],
    ["something-new", /Sign-in failed/],
  ])("turns ?auth_error=%s into a message and clears it from the URL", async (code, message) => {
    window.history.replaceState(null, "", `/?auth_error=${code}#/`);
    vi.spyOn(api, "authMethods").mockResolvedValue({ providers: [], demo: false });
    render(<Login onLogin={() => {}} />);
    expect(screen.getByRole("alert")).toHaveTextContent(message);
    expect(window.location.search).toBe("");
    expect(window.location.hash).toBe("#/");
  });
});
