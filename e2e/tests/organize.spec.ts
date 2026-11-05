import { expect, test } from "@playwright/test";
import { loginAs, newDocument, uniqueTitle } from "./fixtures";

test("recently opened, sorting, duplicate, archive and restore", async ({ page }) => {
  const title = uniqueTitle("Antenna test");
  // Charlie: other specs (run in parallel) never open documents as Charlie, so his
  // "Recently opened" order is stable here.
  await loginAs(page, "charlie");
  await newDocument(page);
  await page.getByLabel("Document title").fill(title);
  await page.getByLabel("Document body").click();
  await page.keyboard.type("EFHW, 49:1 unun");
  // Duplicate and Archive wait for a save so nothing unsaved is lost.
  await expect(page.getByRole("button", { name: "Duplicate" })).toBeDisabled();
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("All changes saved");

  // Duplicate opens an editable copy with the same content.
  await page.getByRole("button", { name: "Duplicate" }).click();
  await expect(page.getByLabel("Document title")).toHaveValue(`Copy of ${title}`);
  await expect(page.getByLabel("Document body")).toContainText("EFHW, 49:1 unun");
  const copyUrl = page.url();

  // Both appear under Recently opened, most recent first.
  await page.getByRole("link", { name: "Documents", exact: true }).click();
  const recent = page.getByRole("region", { name: "Recently opened" });
  await expect(recent.getByRole("link").first()).toHaveText(`Copy of ${title}`);
  await expect(recent.getByRole("link", { name: title, exact: true })).toBeVisible();

  // Sorting applies to the owned list and is remembered across reloads.
  const owned = page.getByRole("region", { name: "Owned by me" });
  await page.getByLabel("Sort by").selectOption("title");
  const titles = await owned.getByRole("link").allTextContents();
  expect(titles).toEqual([...titles].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base", numeric: true })));
  await page.reload();
  await expect(page.getByLabel("Sort by")).toHaveValue("title");

  // Archive the copy: read-only with a banner, gone from lists, listed under Archived.
  await page.goto(copyUrl);
  await page.getByRole("button", { name: "Archive" }).click();
  await expect(page.getByRole("note")).toContainText("Archived");
  await expect(page.getByRole("toolbar", { name: "Formatting" })).toHaveCount(0);
  await expect(page.getByLabel("Document body")).toHaveAttribute("contenteditable", "false");
  await expect(page.getByRole("button", { name: "Save" })).toHaveCount(0);

  await page.getByRole("link", { name: "Documents", exact: true }).click();
  await expect(owned.getByRole("link", { name: title, exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: `Copy of ${title}` })).toHaveCount(0);
  await page.getByRole("button", { name: "Show archived documents" }).click();
  const archived = page.getByRole("region", { name: "Archived" });
  await expect(archived.getByRole("link", { name: `Copy of ${title}` })).toBeVisible();

  // Restore from the list brings it back.
  await archived.getByRole("button", { name: `Restore Copy of ${title}` }).click();
  await expect(owned.getByRole("link", { name: `Copy of ${title}` })).toBeVisible();
  await expect(archived.getByRole("link", { name: `Copy of ${title}` })).toHaveCount(0);

  // And it is editable again.
  await owned.getByRole("link", { name: `Copy of ${title}` }).click();
  await expect(page.getByRole("note")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Save" })).toBeVisible();
});
