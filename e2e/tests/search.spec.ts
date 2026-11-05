import { expect, test, type Page } from "@playwright/test";
import { loginAs, newDocument, uniqueTitle, type DemoUser } from "./fixtures";

const NAMES: Record<DemoUser, string> = {
  alice: "Alice (owner)",
  bob: "Bob (recipient)",
  charlie: "Charlie (no access)",
};

async function switchTo(page: Page, user: DemoUser) {
  await page.goto("/");
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.getByRole("button", { name: NAMES[user] }).click();
  await expect(page.getByText(`Signed in as ${NAMES[user]}`)).toBeVisible();
}

async function writeDocument(page: Page, title: string, body: string) {
  await newDocument(page);
  await page.getByLabel("Document title").fill(title);
  await page.getByLabel("Document body").click();
  await page.keyboard.type(body);
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("All changes saved");
}

test("search finds own and shared documents by title and body, never others'", async ({ page }) => {
  // One word unique to this run, so parallel specs and earlier runs can't add matches.
  const marker = `qsl${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
  const title = `${uniqueTitle("POTA activation")} ${marker.slice(-4)}`;

  await loginAs(page, "alice");
  await writeDocument(page, title, `Worked AO-91 from park K-4392, logged under ${marker} tonight.`);
  await page.getByRole("button", { name: "Share" }).click();
  const share = page.getByRole("dialog", { name: "Share document" });
  await share.getByLabel("Email address").fill("bob@demo.test");
  await share.getByRole("button", { name: "Share", exact: true }).click();
  await expect(share.getByRole("button", { name: `Revoke ${NAMES.bob}` })).toBeVisible();
  await share.getByRole("button", { name: "Close" }).click();

  // Alice finds it by a word from the title and by text in the body, with a snippet.
  await page.getByRole("link", { name: "Documents", exact: true }).click();
  const box = page.getByRole("searchbox", { name: "Search documents" });
  const results = page.getByRole("region", { name: "Search results" });
  await box.fill(marker.toUpperCase());
  await expect(page.getByText("1 document matches")).toBeVisible();
  await expect(results.getByRole("link", { name: title })).toBeVisible();
  await expect(results.getByText(/logged under/)).toBeVisible();
  // Escape returns to the full lists.
  await box.press("Escape");
  await expect(box).toHaveValue("");
  await expect(page.getByRole("region", { name: "Owned by me" })).toBeVisible();

  // Bob, on a phone, finds the shared document with its "View only" badge.
  await page.setViewportSize({ width: 390, height: 844 });
  await switchTo(page, "bob");
  await box.fill(`k-43 ${marker}`);
  await expect(results.getByRole("link", { name: title })).toBeVisible();
  await expect(results.getByText(`View only · ${NAMES.alice}`)).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
  await page.getByRole("button", { name: "Clear" }).click();
  await expect(box).toBeFocused();

  // Charlie can search his own notes but never sees Alice's.
  await page.setViewportSize({ width: 1280, height: 720 });
  await switchTo(page, "charlie");
  const own = uniqueTitle("Charlie log");
  await writeDocument(page, own, "nothing shared here");
  await page.getByRole("link", { name: "Documents", exact: true }).click();
  await box.fill(own);
  await expect(results.getByRole("link", { name: own })).toBeVisible();
  await box.fill(marker);
  await expect(page.getByText(`No documents match “${marker}”.`)).toBeVisible();
  await expect(results).toHaveCount(0);
  await box.fill(title);
  await expect(page.getByText(`No documents match “${title}”.`)).toBeVisible();
});
