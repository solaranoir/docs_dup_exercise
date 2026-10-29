import { expect, type Page } from "@playwright/test";

export type DemoUser = "alice" | "bob" | "charlie";

const NAMES: Record<DemoUser, RegExp> = {
  alice: /^Alice/,
  bob: /^Bob/,
  charlie: /^Charlie/,
};

export async function loginAs(page: Page, user: DemoUser): Promise<void> {
  await page.goto("/");
  await page.getByRole("button", { name: NAMES[user] }).click();
  await expect(page.getByText("Signed in as")).toBeVisible();
}

/** Creates a document via the UI and returns its URL once the editor route is active. */
export async function newDocument(page: Page): Promise<string> {
  await page.getByRole("button", { name: "New document" }).click();
  await expect(page).toHaveURL(/#\/doc\/[\w-]+$/);
  await expect(page.getByLabel("Document body")).toBeVisible();
  return page.url();
}

export const uniqueTitle = (prefix: string) => `${prefix} ${Date.now().toString(36)}`;
