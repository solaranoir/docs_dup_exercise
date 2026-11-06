import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { loginAs, newDocument, uniqueTitle } from "./fixtures";

/** WCAG 2.1 A and AA rules (axe-core). Reports each violation with the elements involved. */
async function expectAccessible(page: Page, where: string, include?: string) {
  let builder = new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]);
  if (include) builder = builder.include(include);
  const { violations } = await builder.analyze();
  const report = violations.map(
    (v) => `${v.id} (${v.impact}): ${v.help}\n  ${v.nodes.map((n) => n.target.join(" ")).join("\n  ")}`,
  );
  expect(report, `${where}:\n${report.join("\n")}`).toEqual([]);
}

test("accessibility: sign-in and not-found pages", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: /^Charlie/ })).toBeVisible();
  await expectAccessible(page, "sign-in");
  await loginAs(page, "charlie");
  await page.goto("/no/such/page");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  await expectAccessible(page, "not found");
});

test("accessibility: My Documents, filters, search, Trash and dialogs", async ({ page }) => {
  const title = uniqueTitle("A11y plan");
  await loginAs(page, "charlie");
  await newDocument(page);
  await page.getByLabel("Document title").fill(title);
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("All changes saved");
  const tags = page.getByRole("region", { name: /Organise/ }).getByLabel("Tags", { exact: true });
  await tags.fill("pota");
  await tags.press("Enter");
  await page.getByRole("link", { name: "Documents", exact: true }).click();
  await expect(page.getByRole("region", { name: "Owned by me" })).toBeVisible();
  await expectAccessible(page, "My Documents");

  await page.getByRole("button", { name: "pota", exact: true }).click();
  await page.getByLabel("Search documents").fill("a11y");
  await expect(page.getByRole("region", { name: "Search results" })).toBeVisible();
  await expectAccessible(page, "filtered search results");
  await page.getByLabel("Search documents").fill("");

  await page.getByRole("button", { name: "Show archived documents" }).click();
  await page.getByRole("button", { name: "Show Trash" }).click();
  await expect(page.getByRole("region", { name: "Trash" })).toBeVisible();
  await expectAccessible(page, "archived and Trash sections");

  for (const [button, dialog] of [
    ["New document", "New document"],
    ["Manage folders", "Folders"],
    ["Import file", "Import file as new document"],
  ] as const) {
    await page.getByRole("button", { name: button }).click();
    const modal = page.getByRole("dialog", { name: dialog });
    await expect(modal).toBeVisible();
    if (dialog === "New document") await modal.getByRole("radio", { name: "POTA Activation Plan" }).check();
    await expectAccessible(page, `${dialog} dialog`, "dialog[open]");
    await modal.getByRole("button", { name: "Close" }).click();
  }
});

test("accessibility: editor, organise panel and its dialogs", async ({ page }) => {
  await loginAs(page, "charlie");
  await page.getByRole("button", { name: "New document" }).click();
  const picker = page.getByRole("dialog", { name: "New document" });
  await picker.getByRole("radio", { name: "Satellite Observation Log" }).check();
  await picker.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("heading", { name: "Reception" })).toBeVisible();
  await expectAccessible(page, "editor (template document)");

  await page.getByLabel("Document body").click();
  await page.keyboard.type(" edited");
  await expectAccessible(page, "editor with unsaved changes");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("All changes saved");

  for (const [button, dialog] of [
    ["Export…", "Export"],
    ["Share", "Share document"],
    ["Import…", "Import into this document"],
  ] as const) {
    await page.getByRole("button", { name: button }).click();
    const modal = page.getByRole("dialog", { name: dialog });
    await expect(modal).toBeVisible();
    await expectAccessible(page, `${dialog} dialog`, "dialog[open]");
    await modal.getByRole("button", { name: "Close" }).click();
  }

  await page.getByRole("button", { name: "Archive" }).click();
  await expect(page.getByRole("note")).toContainText("Archived");
  await expectAccessible(page, "archived (read-only) editor");
});
