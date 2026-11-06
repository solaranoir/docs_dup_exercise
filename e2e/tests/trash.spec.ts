import { expect, test, type Page } from "@playwright/test";
import { loginAs, newDocument, uniqueTitle } from "./fixtures";

async function deleteFromEditor(page: Page, title: string) {
  page.once("dialog", (d) => {
    expect(d.message()).toContain(`Move "${title}" to the Trash? You can restore it for 30 days.`);
    void d.accept();
  });
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByText(`Moved "${title}" to the Trash.`)).toBeVisible();
}

test("trash: delete, undo, restore from Trash, delete forever", async ({ page }) => {
  // Charlie: an isolated user; titles are unique per run.
  const title = uniqueTitle("Trash me");
  await loginAs(page, "charlie");
  const url = await newDocument(page);
  await page.getByLabel("Document title").fill(title);
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("All changes saved");
  const owned = page.getByRole("region", { name: "Owned by me" });

  // Delete, then Undo straight away.
  await deleteFromEditor(page, title);
  await expect(owned.getByRole("link", { name: title })).toHaveCount(0);
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByText("Restored from the Trash.")).toBeVisible();
  await expect(owned.getByRole("link", { name: title })).toBeVisible();

  // Delete again; restore it from the Trash; it opens normally.
  await owned.getByRole("link", { name: title }).click();
  await deleteFromEditor(page, title);
  await page.getByRole("button", { name: "Show Trash" }).click();
  const trash = page.getByRole("region", { name: "Trash" });
  await expect(trash.getByText(title, { exact: true })).toBeVisible();
  await trash.getByRole("button", { name: `Restore ${title}` }).click();
  await expect(trash.getByText(title, { exact: true })).toHaveCount(0);
  await expect(owned.getByRole("link", { name: title })).toBeVisible();
  await owned.getByRole("link", { name: title }).click();
  await expect(page.getByLabel("Document title")).toHaveValue(title);

  // Delete forever: gone from the Trash, and the old link looks missing.
  await deleteFromEditor(page, title);
  await page.getByRole("button", { name: "Show Trash" }).click();
  page.once("dialog", (d) => void d.accept());
  await trash.getByRole("button", { name: `Delete ${title} forever` }).click();
  await expect(trash.getByText(title, { exact: true })).toHaveCount(0);
  await page.goto(url);
  await expect(page.getByRole("alert")).toHaveText("Document not found, or you do not have access to it.");
});
