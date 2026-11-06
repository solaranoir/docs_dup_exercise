import { readFileSync } from "node:fs";
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { loginAs, uniqueTitle } from "./fixtures";

/**
 * The v1.0 acceptance journey (roadmap, Phase 6): "A new user can securely create a document
 * from a template, edit, attach, organize, export, and retrieve it later; another user cannot
 * read it without permission." Plus a session that ends mid-edit, and revocation while the
 * viewer has the document open.
 */
test("v1.0 journey: template → edit → attach → organise → export → retrieve; others locked out", async ({
  browser,
}) => {
  test.setTimeout(90_000);
  const marker = uniqueTitle("K4389").replace(" ", "x"); // one searchable word
  const folder = uniqueTitle("POTA 2026");
  const owner = await browser.newContext();
  const other = await browser.newContext();
  const page = await owner.newPage();
  const bob = await other.newPage();

  // Charlie (owner here) sets up a folder, then creates a POTA plan from the template.
  await loginAs(page, "charlie");
  await page.getByRole("button", { name: "Manage folders" }).click();
  const folders = page.getByRole("dialog", { name: "Folders" });
  await folders.getByLabel("New folder").fill(folder);
  await folders.getByRole("button", { name: "Create" }).click();
  await expect(folders.getByText(folder, { exact: true })).toBeVisible();
  await folders.getByRole("button", { name: "Close" }).click();
  await page.getByRole("button", { name: "New document" }).click();
  const picker = page.getByRole("dialog", { name: "New document" });
  await picker.getByRole("radio", { name: "POTA Activation Plan" }).check();
  await picker.getByRole("button", { name: "Create" }).click();
  await expect(page).toHaveURL(/\/doc\/[\w-]+$/);
  const url = page.url();
  const id = url.split("/").pop()!;
  const title = await page.getByLabel("Document title").inputValue();
  expect(title).toMatch(/^POTA Activation Plan, \d{4}-\d{2}-\d{2}$/);

  // Edit: fill in the park reference.
  const body = page.getByLabel("Document body");
  const line = body.locator("p", { hasText: /^Park reference:/ });
  const box = (await line.boundingBox())!;
  await line.click({ position: { x: box.width - 4, y: box.height / 2 } });
  await page.keyboard.type(marker);
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("All changes saved");

  // Attach a log, file it in the folder and tag it.
  const attachments = page.getByRole("region", { name: "Attachments" });
  await attachments.getByLabel("Attach file").setInputFiles({
    name: "activation-log.txt",
    mimeType: "text/plain",
    buffer: Buffer.from(`${marker} 14.074 FT8\n`),
  });
  await expect(attachments.getByRole("link", { name: /activation-log\.txt/ })).toBeVisible();
  const organise = page.getByRole("region", { name: /Organise/ });
  await organise.getByLabel("Folder").selectOption({ label: folder });
  const tags = organise.getByLabel("Tags", { exact: true });
  await tags.fill("pota");
  await tags.press("Enter");
  await expect(organise.getByRole("button", { name: "Remove tag pota" })).toBeVisible();

  // Export: Markdown with the attachment, as a .zip.
  await page.getByRole("button", { name: "Export…" }).click();
  const downloading = page.waitForEvent("download");
  await page.getByRole("dialog", { name: "Export" }).getByRole("button", { name: "Download Markdown" }).click();
  const zip = await downloading;
  expect(zip.suggestedFilename()).toMatch(/^pota-activation-plan-[\d-]+\.zip$/);
  expect(readFileSync(await zip.path()).subarray(0, 2).toString()).toBe("PK");

  // Another user cannot read it: not via the link, the API, search, or the attachment.
  await loginAs(bob, "bob");
  await bob.goto(url);
  await expect(bob.getByRole("alert")).toHaveText("Document not found, or you do not have access to it.");
  expect((await bob.request.get(`/api/documents/${id}`)).status()).toBe(404);
  expect((await bob.request.get(`/api/documents/${id}/export`)).status()).toBe(404);
  const hits = await bob.request.get(`/api/documents/search?q=${marker}`);
  expect(await hits.json()).toEqual([]);

  // The session ends mid-edit (signed out elsewhere): the edit survives and saves after signing in again.
  await body.click();
  await page.keyboard.press("ControlOrMeta+End");
  await page.keyboard.type(" unsaved-after-signout");
  const elsewhere = await owner.newPage();
  await elsewhere.goto("/");
  await elsewhere.getByRole("button", { name: "Sign out" }).click();
  await expect(elsewhere.getByRole("button", { name: /^Charlie/ })).toBeVisible();
  await page.getByRole("button", { name: "Save" }).click();
  const banner = page.getByRole("alert").filter({ hasText: "You've been signed out." });
  await expect(banner).toBeVisible();
  await expect(body).toContainText("unsaved-after-signout");
  await loginAs(elsewhere, "charlie"); // "Sign in in a new tab"
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("All changes saved");
  await expect(banner).toHaveCount(0);
  await elsewhere.close();

  // Retrieve it later: sign out, sign back in, find it by folder, everything intact.
  await page.goto("/");
  await page.getByRole("button", { name: "Sign out" }).click();
  await loginAs(page, "charlie");
  await page.getByLabel("Folder", { exact: true }).selectOption({ label: folder });
  const owned = page.getByRole("region", { name: "Owned by me" });
  await expect(owned.getByRole("listitem")).toHaveCount(1);
  await owned.getByRole("link", { name: title }).click();
  await expect(body).toContainText(`Park reference: ${marker}`);
  await expect(body).toContainText("unsaved-after-signout");
  const download = page.waitForEvent("download");
  await attachments.getByRole("link", { name: /activation-log\.txt/ }).click();
  expect(readFileSync(await (await download).path(), "utf8")).toBe(`${marker} 14.074 FT8\n`);

  // Share read-only with Bob; his view is accessible and read-only.
  await page.getByRole("button", { name: "Share" }).click();
  const share = page.getByRole("dialog", { name: "Share document" });
  await share.getByLabel("Email address").fill("bob@demo.test");
  await share.getByRole("button", { name: "Share", exact: true }).click();
  const revoke = share.getByRole("button", { name: /^Revoke Bob/ });
  await expect(revoke).toBeVisible();
  await bob.goto(url);
  await expect(bob.getByLabel("Document body")).toContainText(marker);
  await expect(bob.getByLabel("Document body")).toHaveAttribute("contenteditable", "false");
  const scan = await new AxeBuilder({ page: bob }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  expect(scan.violations.map((v) => v.id)).toEqual([]);

  // Revoked while Bob has it open: his next load and the attachment are refused.
  await revoke.click();
  await expect(revoke).toHaveCount(0);
  await bob.reload();
  await expect(bob.getByRole("alert")).toHaveText("Document not found, or you do not have access to it.");
  const atts = await page.request.get(`/api/documents/${id}/attachments`);
  const attId = (await atts.json())[0].id;
  expect((await bob.request.get(`/api/documents/${id}/attachments/${attId}`)).status()).toBe(404);

  await owner.close();
  await other.close();
});
