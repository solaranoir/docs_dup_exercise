import { expect, test } from "@playwright/test";
import { loginAs, newDocument, uniqueTitle } from "./fixtures";

test("personal folders and tags: file, tag, filter by URL, delete folder", async ({ page }) => {
  // Charlie: other specs don't organise as Charlie; names are unique per run anyway.
  const title = uniqueTitle("K-4389 plan");
  const folder = uniqueTitle("POTA");
  await loginAs(page, "charlie");

  // Create a folder from the list page.
  await page.getByRole("button", { name: "Manage folders" }).click();
  const dialog = page.getByRole("dialog", { name: "Folders" });
  await dialog.getByLabel("New folder").fill(folder);
  await dialog.getByRole("button", { name: "Create" }).click();
  await expect(dialog.getByText(folder, { exact: true })).toBeVisible();
  await dialog.getByRole("button", { name: "Close" }).click();

  // File and tag a new document from the editor; organising saves on its own.
  await newDocument(page);
  await page.getByLabel("Document title").fill(title);
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("All changes saved");
  const organise = page.getByRole("region", { name: /Organise/ });
  await organise.getByLabel("Folder").selectOption({ label: folder });
  const tags = organise.getByLabel("Tags", { exact: true });
  await tags.fill("POTA");
  await tags.press("Enter");
  await tags.fill("cw");
  await tags.press("Enter");
  await expect(organise.getByRole("button", { name: "Remove tag pota" })).toBeVisible();
  await expect(organise.getByRole("button", { name: "Remove tag cw" })).toBeVisible();
  await expect(page.getByRole("status")).toHaveText("All changes saved"); // not an edit

  // Reload: both persisted.
  await page.reload();
  await expect(organise.getByLabel("Folder")).toHaveValue(/\d+/);
  await expect(organise.getByRole("button", { name: "Remove tag cw" })).toBeVisible();

  // List shows folder and tags; filters narrow the list and live in the URL.
  await page.getByRole("link", { name: "Documents", exact: true }).click();
  const owned = page.getByRole("region", { name: "Owned by me" });
  const row = owned.getByRole("listitem").filter({ hasText: title });
  await expect(row).toContainText(folder);
  await expect(row).toContainText("pota");
  await page.getByLabel("Folder", { exact: true }).selectOption({ label: folder });
  await expect(page).toHaveURL(/\?folder=\d+/);
  await expect(owned.getByRole("link")).toHaveText([title]);
  await page.getByRole("button", { name: "cw", exact: true }).click();
  await expect(page).toHaveURL(/tag=cw/);
  await page.reload();
  await expect(owned.getByRole("link")).toHaveText([title]);
  await page.getByRole("button", { name: "Clear filters" }).click();
  await expect(page).not.toHaveURL(/folder=|tag=/);

  // Deleting the folder ungroups the document; it is not deleted.
  await page.getByRole("button", { name: "Manage folders" }).click();
  page.once("dialog", (d) => void d.accept());
  await dialog.getByRole("button", { name: `Delete ${folder}` }).click();
  await expect(dialog.getByText(folder, { exact: true })).toHaveCount(0);
  await dialog.getByRole("button", { name: "Close" }).click();
  await expect(row).toBeVisible();
  await expect(row).not.toContainText(folder);
});
