import { expect, test } from "@playwright/test";
import { loginAs, newDocument, uniqueTitle } from "./fixtures";

test("path routes: deep links, back/forward, legacy #/ links, unknown paths", async ({ page }) => {
  const title = uniqueTitle("Routing");
  await loginAs(page, "alice");
  const url = await newDocument(page);
  const path = new URL(url).pathname;
  await page.getByLabel("Document title").fill(title);
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("status")).toHaveText("All changes saved");

  // Back/forward move between list and document without a reload.
  await page.getByRole("link", { name: "Documents", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("region", { name: "Owned by me" }).getByRole("link", { name: title })).toBeVisible();
  await page.goBack();
  await expect(page.getByLabel("Document title")).toHaveValue(title);
  await expect(page).toHaveTitle(`${title} · Solara Docs`);
  await page.goForward();
  await expect(page.getByRole("region", { name: "Owned by me" }).getByRole("link", { name: title })).toBeVisible();

  // A deep link loads directly (dev server / Render rewrite serve index.html).
  await page.goto(path);
  await expect(page.getByLabel("Document title")).toHaveValue(title);

  // Old hash links are rewritten to the path form.
  await page.goto(`/#${path}`);
  await expect(page).toHaveURL(new RegExp(`${path}$`));
  await expect(page.getByLabel("Document title")).toHaveValue(title);

  await page.goto("/no/such/page");
  await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
  await page.getByRole("link", { name: "Go to My Documents" }).click();
  await expect(page.getByRole("heading", { name: "My Documents" })).toBeVisible();
});

test("unsaved edits: in-app navigation asks first and can stay", async ({ page }) => {
  await loginAs(page, "alice");
  const url = await newDocument(page);
  await page.getByLabel("Document body").click();
  await page.keyboard.type("draft");

  page.once("dialog", (d) => void d.dismiss());
  await page.getByRole("link", { name: "Documents", exact: true }).click();
  await expect(page).toHaveURL(url);
  await expect(page.getByLabel("Document body")).toContainText("draft");
});

test("keyboard: skip link, toolbar via Alt+F10, roving focus, Escape back to text", async ({ page }) => {
  await loginAs(page, "alice");
  await newDocument(page);

  // Focus moved to <main> after navigation; the skip link is the first Tab stop on a fresh load.
  await expect(page.locator("main")).toBeFocused();
  await page.reload();
  await expect(page.getByLabel("Document body")).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();

  const body = page.getByLabel("Document body");
  await body.click();
  await page.keyboard.type("hello");
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.press("Alt+F10");
  await expect(page.getByRole("combobox", { name: "Block style" })).toBeFocused();

  await page.keyboard.press("End");
  await expect(page.getByRole("button", { name: "Numbered list" })).toBeFocused();
  await page.keyboard.press("Home");
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  const bold = page.getByRole("button", { name: "Bold" });
  await expect(bold).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(bold).toHaveAttribute("aria-pressed", "true");
  await expect(body.locator("strong")).toHaveText("hello");

  // Escape returns to the text; Alt+F10 comes back to the last-used control.
  await page.keyboard.press("Escape");
  await expect(body).toBeFocused();
  await page.keyboard.press("Alt+F10");
  await expect(bold).toBeFocused();

  // Only one toolbar control is in the Tab order.
  await expect(page.locator('.toolbar [tabindex="0"]')).toHaveCount(1);
});
