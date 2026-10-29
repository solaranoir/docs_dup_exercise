import { expect, test } from "@playwright/test";
import { loginAs, newDocument, uniqueTitle } from "./fixtures";

test("create → format → save → refresh → reopen keeps structure", async ({ page }) => {
  const title = uniqueTitle("Quarterly Notes");
  await loginAs(page, "alice");
  await newDocument(page);

  await page.getByLabel("Document title").fill(title);
  const body = page.getByLabel("Document body");
  await body.click();
  await page.getByLabel("Block style").selectOption("h1");
  await page.keyboard.type("Summary");
  await page.keyboard.press("Enter");
  await page.keyboard.type("plain ");
  await page.keyboard.press("ControlOrMeta+b");
  await page.keyboard.type("bold");
  await page.keyboard.press("ControlOrMeta+b");
  await page.keyboard.type(" ");
  await page.keyboard.press("ControlOrMeta+i");
  await page.keyboard.type("italic");
  await page.keyboard.press("ControlOrMeta+i");
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Bulleted list" }).click();
  await page.keyboard.type("first item");
  await page.keyboard.press("Enter");
  await page.keyboard.type("second item");

  const status = page.getByRole("status");
  await expect(status).toHaveText("Unsaved changes");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(status).toHaveText("All changes saved");

  await page.reload();
  await expect(page.getByLabel("Document title")).toHaveValue(title);
  await expect(body.locator("h1")).toHaveText("Summary");
  await expect(body.locator("strong")).toHaveText("bold");
  await expect(body.locator("em")).toHaveText("italic");
  await expect(body.locator("ul > li")).toHaveText(["first item", "second item"]);

  await page.getByRole("link", { name: "← Documents" }).click();
  const owned = page.getByRole("region", { name: "Owned by me" });
  await expect(owned.getByRole("link", { name: title })).toBeVisible();
});

test("Ctrl/Cmd+S saves and in-app navigation warns about unsaved edits", async ({ page }) => {
  await loginAs(page, "alice");
  await newDocument(page);
  await page.getByLabel("Document body").click();
  await page.keyboard.type("draft text");
  await page.keyboard.press("ControlOrMeta+s");
  await expect(page.getByRole("status")).toHaveText("All changes saved");

  await page.keyboard.type(" more");
  let prompted = false;
  page.once("dialog", (dialog) => {
    prompted = true;
    void dialog.dismiss();
  });
  await page.getByRole("link", { name: "← Documents" }).click();
  expect(prompted).toBe(true);
  await expect(page).toHaveURL(/#\/doc\//);
});

test("stale save shows a conflict with a recovery path", async ({ page, context }) => {
  await loginAs(page, "alice");
  const url = await newDocument(page);

  const other = await context.newPage();
  await other.goto(url);
  await other.getByLabel("Document body").click();
  await other.keyboard.type("from tab two");
  await other.getByRole("button", { name: "Save" }).click();
  await expect(other.getByRole("status")).toHaveText("All changes saved");

  await page.getByLabel("Document body").click();
  await page.keyboard.type("from tab one");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText(/Conflict/);
  await expect(page.getByRole("alert")).toContainText("changed since you opened it");

  page.once("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: "Reload latest version" }).click();
  await expect(page.getByLabel("Document body")).toContainText("from tab two");
  await expect(page.getByRole("status")).toHaveText("All changes saved");
});

test("documents of other users are not reachable", async ({ page }) => {
  await loginAs(page, "alice");
  const url = await newDocument(page);
  await page.getByRole("button", { name: "Switch user" }).click();
  await page.getByRole("button", { name: /^Charlie/ }).click();
  await expect(page.getByText("Charlie (no access)")).toBeVisible();
  await page.goto(url);
  await expect(page.getByRole("alert")).toContainText("not found");
});
