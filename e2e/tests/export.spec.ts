import { readFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";
import { loginAs, newDocument, uniqueTitle } from "./fixtures";

async function exportMarkdown(page: Page) {
  await page.getByRole("button", { name: "Export…" }).click();
  const dialog = page.getByRole("dialog", { name: "Export" });
  const downloading = page.waitForEvent("download");
  await dialog.getByRole("button", { name: "Download Markdown" }).click();
  const file = await downloading;
  await expect(dialog).toBeHidden();
  return { name: file.suggestedFilename(), path: await file.path() };
}

test("export: Markdown, Markdown with attachments, print layout, export all", async ({ page }) => {
  // Charlie: an isolated user for these specs; titles are unique per run.
  const title = uniqueTitle("Export plan");
  await loginAs(page, "charlie");
  await newDocument(page);
  await page.getByLabel("Document title").fill(title);
  const body = page.getByLabel("Document body");
  await body.click();
  await page.keyboard.type("K-4389 <park> & [map], "); // typed "# " would become a heading
  await page.keyboard.press("ControlOrMeta+b");
  await page.keyboard.type("bold");

  // Unsaved edits: Markdown waits for a save; printing is still available.
  await page.getByRole("button", { name: "Export…" }).click();
  const dialog = page.getByRole("dialog", { name: "Export" });
  await expect(dialog.getByRole("button", { name: "Download Markdown" })).toBeDisabled();
  await expect(dialog.getByRole("button", { name: "Print or save as PDF" })).toBeEnabled();
  await dialog.getByRole("button", { name: "Close" }).click();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("All changes saved");

  // No attachments: a .md named after the title, with Markdown syntax in text escaped.
  const md = await exportMarkdown(page);
  expect(md.name).toMatch(/^export-plan-[a-z0-9-]+\.md$/);
  expect(readFileSync(md.path, "utf8")).toBe(`# ${title}\n\nK-4389 \\<park\\> \\& \\[map\\], **bold**\n`);

  // With an attachment: a .zip.
  const panel = page.getByRole("region", { name: "Attachments" });
  await panel.getByLabel("Attach file").setInputFiles({
    name: "swr-readings.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("14.074 1.3:1\n"),
  });
  await expect(panel.getByRole("link", { name: /swr-readings\.txt/ })).toBeVisible();
  const zip = await exportMarkdown(page);
  expect(zip.name).toMatch(/^export-plan-[a-z0-9-]+\.zip$/);
  expect(readFileSync(zip.path).subarray(0, 2).toString()).toBe("PK");

  // Print layout: only the title and the document, dark on white.
  await page.emulateMedia({ media: "print" });
  await expect(page.locator(".app-header")).toBeHidden();
  await expect(page.getByRole("button", { name: "Save" })).toBeHidden();
  await expect(panel).toBeHidden();
  await expect(page.getByLabel("Document title")).toBeVisible();
  await expect(body).toHaveCSS("color", "rgb(17, 17, 17)");
  await page.emulateMedia({ media: "screen" });

  // Export all from My Documents.
  await page.getByRole("link", { name: "Documents", exact: true }).click();
  const downloading = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export all" }).click();
  const all = await downloading;
  await expect(page.getByText(/Export failed/)).toHaveCount(0);
  expect(all.suggestedFilename()).toMatch(/^solara-docs-export-\d{4}-\d{2}-\d{2}\.zip$/);
});
