import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";
import { FIXTURES, loginAs, newDocument } from "./fixtures";

test("attach, download, persist across reload, and remove a file", async ({ page }) => {
  await loginAs(page, "alice");
  await newDocument(page);
  const panel = page.getByRole("region", { name: "Attachments" });
  await expect(panel.getByText("No attachments.")).toBeVisible();

  await panel.getByLabel("Attach file").setInputFiles(`${FIXTURES}/sample.txt`);
  const link = panel.getByRole("link", { name: "sample.txt" });
  await expect(link).toBeVisible();

  const [download] = await Promise.all([page.waitForEvent("download"), link.click()]);
  expect(download.suggestedFilename()).toBe("sample.txt");
  const downloaded = await readFile((await download.path())!);
  expect(downloaded.equals(await readFile(`${FIXTURES}/sample.txt`))).toBe(true);

  await page.reload();
  await expect(panel.getByRole("link", { name: "sample.txt" })).toBeVisible();

  page.once("dialog", (d) => void d.accept());
  await panel.getByRole("button", { name: "Remove sample.txt" }).click();
  await expect(panel.getByText("No attachments.")).toBeVisible();
});

test("rejected attachment shows an error", async ({ page }) => {
  await loginAs(page, "alice");
  await newDocument(page);
  const panel = page.getByRole("region", { name: "Attachments" });
  await panel.getByLabel("Attach file").setInputFiles({
    name: "script.js",
    mimeType: "text/javascript",
    buffer: Buffer.from("alert(1)"),
  });
  await expect(panel.getByRole("alert")).toContainText("Unsupported file type");
});
