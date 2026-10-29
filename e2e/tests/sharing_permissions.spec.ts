import { expect, test, type Page } from "@playwright/test";
import { FIXTURES, loginAs, newDocument, uniqueTitle, type DemoUser } from "./fixtures";

const NAMES: Record<DemoUser, string> = {
  alice: "Alice (owner)",
  bob: "Bob (recipient)",
  charlie: "Charlie (no access)",
};

async function switchTo(page: Page, user: DemoUser) {
  await page.goto("/#/");
  await page.getByRole("button", { name: "Switch user" }).click();
  await page.getByRole("button", { name: NAMES[user] }).click();
  await expect(page.getByText(`Signed in as ${NAMES[user]}`)).toBeVisible();
}

test("Alice shares with Bob (read-only), Charlie is denied, revoke removes access", async ({ page }) => {
  const title = uniqueTitle("Quarterly Notes");

  // Alice creates a document with content and an attachment, then shares it with Bob.
  await loginAs(page, "alice");
  const url = await newDocument(page);
  const id = url.split("/").pop()!;
  await page.getByLabel("Document title").fill(title);
  await page.getByLabel("Document body").click();
  await page.keyboard.type("Shared content");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("All changes saved");
  await page.getByRole("region", { name: "Attachments" }).getByLabel("Attach file").setInputFiles(`${FIXTURES}/sample.txt`);
  await expect(page.getByRole("link", { name: "sample.txt" })).toBeVisible();

  await page.getByRole("button", { name: "Share" }).click();
  const share = page.getByRole("dialog", { name: "Share document" });
  await share.getByRole("button", { name: `Share with ${NAMES.bob}` }).click();
  await expect(share.getByRole("button", { name: `Revoke ${NAMES.bob}` })).toBeVisible();
  await share.getByRole("button", { name: "Close" }).click();

  // Bob sees it under Shared with me and can only read.
  await switchTo(page, "bob");
  const sharedSection = page.getByRole("region", { name: "Shared with me" });
  await expect(sharedSection.getByRole("link", { name: title })).toBeVisible();
  await expect(sharedSection.getByText(`View only · ${NAMES.alice}`)).toBeVisible();
  await sharedSection.getByRole("link", { name: title }).click();
  await expect(page.getByText(`View only · shared by ${NAMES.alice}`)).toBeVisible();
  await expect(page.getByLabel("Document body")).toContainText("Shared content");
  await expect(page.getByLabel("Document body")).toHaveAttribute("contenteditable", "false");
  await expect(page.getByLabel("Document title")).toHaveAttribute("readonly", "");
  await expect(page.getByRole("button", { name: "Save" })).toHaveCount(0);
  await expect(page.getByRole("toolbar", { name: "Formatting" })).toHaveCount(0);
  await expect(page.getByLabel("Attach file")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "sample.txt" })).toBeVisible();

  // Direct API attempts are refused server-side, not just hidden in the UI.
  const patch = await page.request.patch(`/api/documents/${id}`, {
    data: { expected_revision: 2, title: "Bob was here" },
  });
  expect(patch.status()).toBe(403);
  const reshare = await page.request.post(`/api/documents/${id}/grants`, { data: { user_id: 3 } });
  expect(reshare.status()).toBe(403);

  // Charlie cannot read it, via UI or API.
  await switchTo(page, "charlie");
  await expect(page.getByRole("region", { name: "Shared with me" }).getByText("Nothing has been shared")).toBeVisible();
  await page.goto(url);
  await expect(page.getByRole("alert")).toContainText("not found");
  expect((await page.request.get(`/api/documents/${id}`)).status()).toBe(404);

  // Alice revokes; Bob loses access.
  await switchTo(page, "alice");
  await page.goto(url);
  await page.getByRole("button", { name: "Share" }).click();
  await page.getByRole("button", { name: `Revoke ${NAMES.bob}` }).click();
  await expect(page.getByRole("button", { name: `Share with ${NAMES.bob}` })).toBeVisible();

  await switchTo(page, "bob");
  await expect(page.getByRole("link", { name: title })).toHaveCount(0);
  expect((await page.request.get(`/api/documents/${id}`)).status()).toBe(404);
});
